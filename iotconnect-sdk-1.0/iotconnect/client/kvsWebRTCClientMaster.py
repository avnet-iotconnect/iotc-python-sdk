import argparse
import asyncio
import boto3
import json
import platform
import websockets
from aiortc import (
    RTCConfiguration,
    RTCIceServer,
    RTCPeerConnection,
    RTCSessionDescription,
    MediaStreamTrack,
)
from aiortc.contrib.media import MediaBlackhole, MediaPlayer, MediaRelay
from aiortc.sdp import candidate_from_sdp
from base64 import b64decode, b64encode
from botocore.auth import SigV4QueryAuth
from botocore.awsrequest import AWSRequest
from botocore.credentials import Credentials
from botocore.session import Session
import os
import sys
import logging
import requests
from typing import Dict, Optional
from datetime import datetime, timedelta, timezone

import aioice.ice

# aioice's RFC 7675 consent-freshness check sends a STUN request every ~5s with
# zero retransmissions and tears the connection down after 6 consecutive failures
# (~30s) - too little slack for a device whose event loop briefly stalls under
# encoding load. Raise the failure budget so a transient stall doesn't kill an
# otherwise-healthy connection. See aiortc/aioice#58.
aioice.ice.CONSENT_FAILURES = int(os.getenv('CONSENT_FAILURES', '60'))

logging.basicConfig(level=logging.INFO, stream=sys.stdout)

print("### CUSTOM KVS WEBRTC CODE LOADED ..........")

class DebugVideoTrack(MediaStreamTrack):
    """
    Thin wrapper around a video track that tells us whether
    frames are still flowing through a particular point.
    """

    kind = "video"

    def __init__(self, track, name):
        super().__init__()
        self.track = track
        self.name = name
        self.frame_count = 0
        self.last_log = 0

    async def recv(self):
        frame = await self.track.recv()

        self.frame_count += 1

        # Log every 30 frames (~1 second at 30 FPS)
        if self.frame_count - self.last_log >= 30:
            self.last_log = self.frame_count

            print(
                f"[VIDEO_DEBUG] {self.name}: "
                f"frame={self.frame_count}, "
                f"pts={frame.pts}, "
                f"time_base={frame.time_base}"
            )

        return frame

class MediaTrackManager:
    def __init__(self, file_path=None):
        self.file_path = file_path
        self.device = os.getenv('CAMERA_DEVICE')
        self.width = int(os.getenv('CAMERA_WIDTH', '1280'))
        self.height = int(os.getenv('CAMERA_HEIGHT', '720'))
        self.framerate = int(os.getenv('CAMERA_FRAMERATE', '30'))
        self.input_format = os.getenv('CAMERA_INPUT_FORMAT', 'mjpeg')
        self.relay = MediaRelay()
        self.media = None

    def _create_media_source(self):
        options = {
            'framerate': str(self.framerate),
            'video_size': f'{self.width}x{self.height}',
            'input_format': self.input_format,
        }
        system = platform.system()

        if self.file_path and not os.path.exists(self.file_path):
            raise FileNotFoundError(f"The file {self.file_path} does not exist.")

        if system == 'Darwin':
            self.media = (
                MediaPlayer('default:default', format='avfoundation', options=options)
                if not self.file_path
                else MediaPlayer(self.file_path)
            )
        elif system == 'Windows':
            self.media = MediaPlayer(
                self.device or 'video=Integrated Camera',
                format='dshow',
                options=options
            )
        elif system == 'Linux':
            self.media = (
            MediaPlayer(self.device or '/dev/video0', format='v4l2', options=options)
            if not self.file_path
            else MediaPlayer(self.file_path)
        )

      
        else:
            raise NotImplementedError(f"Unsupported platform: {system}")

        if self.media.audio is None and self.media.video is None:
            raise ValueError(
                "Neither audio nor video track could be created from the source."
            )

        print(
            f"Media source created: audio={self.media.audio is not None}, "
            f"video={self.media.video is not None}"
        )

    def create_media_track_for_viewer(self):

        if self.media is None:
            self._create_media_source()

        audio_track = (
            self.relay.subscribe(self.media.audio)
            if self.media.audio
            else None
        )

        source_video = self.media.video

        if source_video:
            source_video = DebugVideoTrack(
                source_video,
                "SOURCE"
            )

        video_track = (
            self.relay.subscribe(source_video)
            if source_video
            else None
        )

        if video_track:
            video_track = DebugVideoTrack(
                video_track,
                "RELAY_TO_WEBRTC"
            )

        if audio_track is None and video_track is None:
            raise ValueError(
                "Neither audio nor video track could be created "
                "from the source."
            )

        print(
            f"Created media relay proxy for viewer: "
            f"audio={audio_track is not None}, "
            f"video={video_track is not None}"
        )

        return audio_track, video_track


class KinesisVideoClient:
    def __init__(self, client_id, region, channel_arn, credentials, file_path=None, credential_provider=None):
        self.client_id = client_id
        self.region = region
        self.channel_arn = channel_arn
        self.credentials = credentials
        self.credential_provider = credential_provider
        self.credentials_expiration = None
        if credentials and credentials.get('expiration'):
            self.credentials_expiration = datetime.fromisoformat(
                credentials['expiration'].replace('Z', '+00:00')
            )
        self.media_manager = MediaTrackManager(file_path)
        self.endpoints = None
        self.endpoint_https = None
        self.endpoint_wss = None
        self.ice_servers = None
        self.PCMap = {}
        self.DCMap = {}

    def _refresh_credentials_if_needed(self):
        # IoT role-alias temporary credentials expire (typically ~1hr). Without
        # this, a long-running Master starts failing every API call and every
        # reconnect once the initial credentials go stale.
        if not self.credential_provider:
            return
        buffer = timedelta(seconds=int(os.getenv('CRED_REFRESH_BUFFER_SECONDS', '300')))
        if self.credentials_expiration is None or datetime.now(timezone.utc) >= (self.credentials_expiration - buffer):
            new_credentials = self.credential_provider.get_temporary_credentials()
            if new_credentials:
                self.credentials = new_credentials
                self.credentials_expiration = datetime.fromisoformat(
                    self.credentials['expiration'].replace('Z', '+00:00')
                )
            else:
                print("Warning: failed to refresh IoT credentials, continuing with existing credentials")

    def _client_kwargs(self):
        self._refresh_credentials_if_needed()
        if self.credentials:
            return {
                'region_name': self.region,
                'aws_access_key_id': self.credentials['accessKeyId'],
                'aws_secret_access_key': self.credentials['secretAccessKey'],
                'aws_session_token': self.credentials['sessionToken'],
            }
        return {'region_name': self.region}

    def get_signaling_channel_endpoint(self):
        if self.endpoints is None:  # Check if endpoints are already fetched
            kinesisvideo = boto3.client('kinesisvideo', **self._client_kwargs())
            endpoints = kinesisvideo.get_signaling_channel_endpoint(
                ChannelARN=self.channel_arn,
                SingleMasterChannelEndpointConfiguration={'Protocols': ['HTTPS', 'WSS'], 'Role': 'MASTER'}
            )
            self.endpoints = {
                'HTTPS': next(o['ResourceEndpoint'] for o in endpoints['ResourceEndpointList'] if o['Protocol'] == 'HTTPS'),
                'WSS': next(o['ResourceEndpoint'] for o in endpoints['ResourceEndpointList'] if o['Protocol'] == 'WSS')
            }
            self.endpoint_https = self.endpoints['HTTPS']
            self.endpoint_wss = self.endpoints['WSS']
        return self.endpoints

    def prepare_ice_servers(self):
        kinesis_video_signaling = boto3.client('kinesis-video-signaling',
                                               endpoint_url=self.endpoint_https,
                                               **self._client_kwargs())
        ice_server_config = kinesis_video_signaling.get_ice_server_config(
            ChannelARN=self.channel_arn,
            ClientId='MASTER'
        )

        iceServers = [RTCIceServer(urls=f'stun:stun.kinesisvideo.{self.region}.amazonaws.com:443')]
        for iceServer in ice_server_config['IceServerList']:
            iceServers.append(RTCIceServer(
                urls=iceServer['Uris'],
                username=iceServer['Username'],
                credential=iceServer['Password']
            ))
        self.ice_servers = iceServers

        return self.ice_servers

    def create_wss_url(self):
        self._refresh_credentials_if_needed()
        if self.credentials:
            auth_credentials = Credentials(
                access_key=self.credentials['accessKeyId'],
                secret_key=self.credentials['secretAccessKey'],
                token=self.credentials['sessionToken']
            )
        else:
            session = Session()
            auth_credentials = session.get_credentials()

        SigV4 = SigV4QueryAuth(auth_credentials, 'kinesisvideo', self.region, 299)
        aws_request = AWSRequest(
            method='GET',
            url=self.endpoint_wss,
            params={'X-Amz-ChannelARN': self.channel_arn, 'X-Amz-ClientId': self.client_id}
        )
        SigV4.add_auth(aws_request)
        PreparedRequest = aws_request.prepare()
        return PreparedRequest.url

    def decode_msg(self, msg):
        try:
            data = json.loads(msg)
            payload = json.loads(b64decode(data['messagePayload'].encode('ascii')).decode('ascii'))
            return data['messageType'], payload, data.get('senderClientId')
        except json.decoder.JSONDecodeError:
            return '', {}, ''

    def encode_msg(self, action, payload, client_id):
        return json.dumps({
            'action': action,
            'messagePayload': b64encode(json.dumps(payload.__dict__).encode('ascii')).decode('ascii'),
            'recipientClientId': client_id,
        })

    async def handle_sdp_offer(self, payload, client_id, websocket):
        # Create a separate MediaRelay proxy for this viewer while sharing
        # the same underlying MediaPlayer/camera source.
        audio_track, video_track = self.media_manager.create_media_track_for_viewer()

        iceServers = self.prepare_ice_servers()
        configuration = RTCConfiguration(iceServers=iceServers)
        pc = RTCPeerConnection(configuration=configuration)
        self.DCMap[client_id] = pc.createDataChannel('kvsDataChannel')
        self.PCMap[client_id] = pc

        @pc.on('connectionstatechange')
        async def on_connectionstatechange():
            #if client_id in self.PCMap:
                #print(f'[{client_id}] connectionState: {self.PCMap[client_id].connectionState}')
            print("on connection state change event...")
            print(
                f"[{client_id}] "
                f"connectionState={pc.connectionState}, "
                f"iceConnectionState={pc.iceConnectionState}, "
                f"signalingState={pc.signalingState}"
            )

        @pc.on('iceconnectionstatechange')
        async def on_iceconnectionstatechange():
            print(f"[{client_id}] ICE={pc.iceConnectionState}")


        @pc.on('icegatheringstatechange')
        async def on_icegatheringstatechange():
            if client_id in self.PCMap:
                print(f'[{client_id}] iceGatheringState: {self.PCMap[client_id].iceGatheringState}')

        @pc.on('signalingstatechange')
        async def on_signalingstatechange():
            if client_id in self.PCMap:
                print(f'[{client_id}] signalingState: {self.PCMap[client_id].signalingState}')

        @pc.on('track')
        def on_track(track):
            MediaBlackhole().addTrack(track)

        @pc.on('datachannel')
        async def on_datachannel(channel):
            @channel.on('message')
            def on_message(dc_message):
                for i in self.PCMap:
                    if self.DCMap[i].readyState == 'open':
                        try:
                            self.DCMap[i].send(f'broadcast: {dc_message}')
                        except Exception as e:
                            print(f"Error sending message: {e}")
                    else:
                        print(f"Data channel {i} is not open. Current state: {self.DCMap[i].readyState}")
                print(f'[{channel.label}] datachannel_message: {dc_message}')

        if audio_track:
            self.PCMap[client_id].addTrack(audio_track)
        if video_track:
            self.PCMap[client_id].addTrack(video_track)

        await self.PCMap[client_id].setRemoteDescription(RTCSessionDescription(
            sdp=payload['sdp'],
            type=payload['type']
        ))
        await self.PCMap[client_id].setLocalDescription(await self.PCMap[client_id].createAnswer())
        await websocket.send(self.encode_msg('SDP_ANSWER', self.PCMap[client_id].localDescription, client_id))

    async def handle_ice_candidate(self, payload, client_id):
        if client_id in self.PCMap:
            candidate = candidate_from_sdp(payload['candidate'])
            candidate.sdpMid = payload['sdpMid']
            candidate.sdpMLineIndex = payload['sdpMLineIndex']
            await self.PCMap[client_id].addIceCandidate(candidate)

    async def signaling_client(self):
        self.get_signaling_channel_endpoint()
        wss_url = self.create_wss_url()

        while True:
            try:
                async with websockets.connect(wss_url) as websocket:
                    print('Signaling Server Connected!')
                    async for message in websocket:
                        msg_type, payload, client_id = self.decode_msg(message)
                        if msg_type == 'SDP_OFFER':
                            await self.handle_sdp_offer(payload, client_id, websocket)
                        elif msg_type == 'ICE_CANDIDATE':
                            await self.handle_ice_candidate(payload, client_id)
            except websockets.ConnectionClosed:
                print('Connection closed, reconnecting...')
                wss_url = self.create_wss_url()
                continue


class IoTCredentialProvider:
    def __init__(self, endpoint: str, region: str, thing_name: str, role_alias: str,
                 cert_path: str, key_path: str, root_ca_path: str):
        self.endpoint = endpoint
        self.region = region
        self.thing_name = thing_name
        self.role_alias = role_alias
        self.cert_path = cert_path
        self.key_path = key_path
        self.root_ca_path = root_ca_path

    def get_temporary_credentials(self) -> Optional[Dict[str, str]]:
        url = f"https://{self.endpoint}/role-aliases/{self.role_alias}/credentials"
        headers = {'x-amzn-iot-thingname': self.thing_name}

        try:
            response = requests.get(
                url,
                headers=headers,
                cert=(self.cert_path, self.key_path),
                verify=self.root_ca_path,
                timeout=(10, 20)  # 10 seconds for connecting, 20 seconds for reading
            )

            if response.status_code == 200:
                credentials = response.json()['credentials']
                print("Temporary credentials obtained successfully.")
                return credentials
            else:
                print(f"Failed to obtain credentials. Status code: {response.status_code}")
                print(f"Response: {response.text}")
                return None

        except requests.exceptions.RequestException as e:
            print(f"An error occurred: {e}")
            return None


async def run_client(client):
    await client.signaling_client()

async def main():
    parser = argparse.ArgumentParser(description='Kinesis Video Streams WebRTC Client')
    parser.add_argument('--channel-arn', type=str, required=True, help='the ARN of the signaling channel')
    parser.add_argument('--file-path', type=str, help='the path to video file to play (optional)')
    parser.add_argument('--aws-region', type=str, default=os.getenv('AWS_DEFAULT_REGION'),
                         help='AWS region (or set AWS_DEFAULT_REGION)')
    parser.add_argument('--use-device-certs', action='store_true',
                         help='Fetch temporary credentials via AWS IoT cert + Role Alias instead of the default AWS credential chain')
    parser.add_argument('--iot-credential-provider', type=str, default=os.getenv('IOT_CREDENTIAL_PROVIDER'),
                         help='AWS IoT credentials-provider endpoint host (or set IOT_CREDENTIAL_PROVIDER)')
    parser.add_argument('--thing-name', type=str, default=os.getenv('THING_NAME'),
                         help='AWS IoT Thing name (or set THING_NAME)')
    parser.add_argument('--role-alias', type=str, default=os.getenv('ROLE_ALIAS'),
                         help='AWS IoT Role Alias name (or set ROLE_ALIAS)')
    parser.add_argument('--cert-file', type=str, default=os.getenv('CERT_FILE'),
                         help='Path to the device certificate (or set CERT_FILE)')
    parser.add_argument('--key-file', type=str, default=os.getenv('KEY_FILE'),
                         help='Path to the device private key (or set KEY_FILE)')
    parser.add_argument('--root-ca', type=str, default=os.getenv('ROOT_CA'),
                         help='Path to the Amazon Root CA certificate (or set ROOT_CA)')
    args = parser.parse_args()

    if not args.aws_region:
        raise SystemExit("--aws-region is required (or set AWS_DEFAULT_REGION).")

    if args.use_device_certs:
        required = {
            "--iot-credential-provider": args.iot_credential_provider,
            "--thing-name": args.thing_name,
            "--role-alias": args.role_alias,
            "--cert-file": args.cert_file,
            "--key-file": args.key_file,
            "--root-ca": args.root_ca,
        }
        missing = [name for name, value in required.items() if not value]
        if missing:
            raise SystemExit(f"Missing required values for --use-device-certs: {', '.join(missing)}")

        provider = IoTCredentialProvider(
            endpoint=args.iot_credential_provider,
            region=args.aws_region,
            thing_name=args.thing_name,
            role_alias=args.role_alias,
            cert_path=args.cert_file,
            key_path=args.key_file,
            root_ca_path=args.root_ca
        )
        credentials = provider.get_temporary_credentials()
        if not credentials:
            raise Exception("Failed to obtain temporary credentials")
    else:
        provider = None
        credentials = None

    client = KinesisVideoClient(
        client_id= "MASTER",
        region=args.aws_region,
        channel_arn=args.channel_arn,
        credentials=credentials,
        file_path=args.file_path,
        credential_provider=provider,
    )

    await run_client(client)

if __name__ == '__main__':
    asyncio.run(main())
