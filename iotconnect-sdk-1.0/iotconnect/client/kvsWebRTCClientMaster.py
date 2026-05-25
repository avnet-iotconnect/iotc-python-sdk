import argparse
import asyncio
import boto3
import json
import platform
import websockets
from aiortc import RTCConfiguration, RTCIceServer, RTCPeerConnection, RTCSessionDescription
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
from dotenv import load_dotenv

logging.basicConfig(level=logging.INFO, stream=sys.stdout)

# Construct script_output_path
script_output_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '../../infra/script-output')

load_dotenv(dotenv_path=f"{script_output_path}/.env")  # take environment variables from .env.
IOT_CREDENTIAL_PROVIDER = os.getenv('IOT_CREDENTIAL_PROVIDER')
THING_NAME = os.getenv('THING_NAME')
ROLE_ALIAS = os.getenv('ROLE_ALIAS')
CERT_FILE = f"{script_output_path}/{os.getenv('CERT_FILE')}"
KEY_FILE = f"{script_output_path}/{os.getenv('KEY_FILE')}"
ROOT_CA = f"{script_output_path}/{os.getenv('ROOT_CA')}"
AWS_DEFAULT_REGION = os.getenv('AWS_DEFAULT_REGION')


class MediaTrackManager:
    """
    Manages a single media source (camera or file) and uses MediaRelay to
    provide independent track subscriptions for each viewer.
    Each viewer gets its own relay subscription so they don't interfere.
    """
    def __init__(self, file_path=None, video_width='640', video_height='480', framerate='15'):
        self.file_path = file_path
        self.video_width = video_width
        self.video_height = video_height
        self.framerate = framerate
        self._relay = MediaRelay()
        self._media = None
        self._started = False

    def _start_media(self):
        """Start the media source once."""
        if self._started:
            return

        options = {'framerate': self.framerate, 'video_size': f'{self.video_width}x{self.video_height}'}
        system = platform.system()

        if self.file_path and not os.path.exists(self.file_path):
            raise FileNotFoundError(f"The file {self.file_path} does not exist.")

        if system == 'Darwin':
            self._media = MediaPlayer('default:default', format='avfoundation', options=options) if not self.file_path else MediaPlayer(self.file_path)
        elif system == 'Windows':
            self._media = MediaPlayer('video=Integrated Camera', format='dshow', options=options)
        elif system == 'Linux':
            self._media = MediaPlayer('/dev/video0', format='v4l2', options=options) if not self.file_path else MediaPlayer(self.file_path)
        else:
            raise NotImplementedError(f"Unsupported platform: {system}")

        self._started = True
        print(f"MediaTrackManager: Media source started ({self.video_width}x{self.video_height} @ {self.framerate}fps)")

    def get_tracks_for_viewer(self):
        """
        Returns a fresh pair of (audio_track, video_track) relay subscriptions
        for a new viewer. Each viewer gets independent tracks from the same source.
        """
        self._start_media()

        audio_track = self._relay.subscribe(self._media.audio) if self._media.audio else None
        video_track = self._relay.subscribe(self._media.video) if self._media.video else None

        if audio_track is None and video_track is None:
            raise ValueError("Neither audio nor video track could be created from the source.")

        return audio_track, video_track


class KinesisVideoClient:
    def __init__(self, client_id, region, channel_arn, credentials, file_path=None,
                 video_width='640', video_height='480', framerate='15'):
        self.client_id = client_id
        self.region = region
        self.channel_arn = channel_arn
        self.credentials = credentials
        self.media_manager = MediaTrackManager(
            file_path=file_path,
            video_width=video_width,
            video_height=video_height,
            framerate=framerate
        )
        if self.credentials:
            self.kinesisvideo = boto3.client('kinesisvideo',
                                             region_name=self.region,
                                             aws_access_key_id=self.credentials['accessKeyId'],
                                             aws_secret_access_key=self.credentials['secretAccessKey'],
                                             aws_session_token=self.credentials['sessionToken']
                                             )
        else:
            self.kinesisvideo = boto3.client('kinesisvideo', region_name=self.region)
        self.endpoints = None
        self.endpoint_https = None
        self.endpoint_wss = None
        self.PCMap = {}
        self.DCMap = {}

    def get_signaling_channel_endpoint(self):
        if self.endpoints is None:
            endpoints = self.kinesisvideo.get_signaling_channel_endpoint(
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

    def fetch_fresh_ice_servers(self):
        """
        Fetch fresh ICE/TURN server credentials from KVS for each new viewer.
        TURN credentials are session-bound, so each viewer needs its own set.
        """
        try:
            if self.credentials:
                kinesis_video_signaling = boto3.client('kinesis-video-signaling',
                                                       endpoint_url=self.endpoint_https,
                                                       region_name=self.region,
                                                       aws_access_key_id=self.credentials['accessKeyId'],
                                                       aws_secret_access_key=self.credentials['secretAccessKey'],
                                                       aws_session_token=self.credentials['sessionToken']
                                                       )
            else:
                kinesis_video_signaling = boto3.client('kinesis-video-signaling',
                                                       endpoint_url=self.endpoint_https,
                                                       region_name=self.region)

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

            print(f"Fetched fresh ICE servers: {len(iceServers)} servers (1 STUN + {len(iceServers)-1} TURN)")
            return iceServers

        except Exception as e:
            print(f"Error fetching ICE servers: {e}")
            # Fallback to STUN only
            return [RTCIceServer(urls=f'stun:stun.kinesisvideo.{self.region}.amazonaws.com:443')]

    def create_wss_url(self):
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

    async def cleanup_peer(self, client_id):
        """Clean up a disconnected peer's resources."""
        if client_id in self.PCMap:
            try:
                await self.PCMap[client_id].close()
            except Exception:
                pass
            del self.PCMap[client_id]
        if client_id in self.DCMap:
            del self.DCMap[client_id]
        print(f"[{client_id}] Peer cleaned up. Active viewers: {len(self.PCMap)}")

    async def handle_sdp_offer(self, payload, client_id, websocket):
        """
        Handle an SDP offer from a viewer.
        - Fetches FRESH ICE servers for this specific viewer
        - Creates a new relay subscription for media tracks
        - Cleans up any existing connection for this client_id
        """
        # Clean up existing connection for this viewer (reconnect scenario)
        if client_id in self.PCMap:
            print(f"[{client_id}] Viewer reconnecting, cleaning up old connection...")
            await self.cleanup_peer(client_id)

        # Fetch fresh ICE/TURN credentials for this viewer
        iceServers = self.fetch_fresh_ice_servers()
        configuration = RTCConfiguration(iceServers=iceServers)
        pc = RTCPeerConnection(configuration=configuration)
        self.DCMap[client_id] = pc.createDataChannel('kvsDataChannel')
        self.PCMap[client_id] = pc

        @pc.on('connectionstatechange')
        async def on_connectionstatechange():
            if client_id in self.PCMap:
                state = self.PCMap[client_id].connectionState
                print(f'[{client_id}] connectionState: {state}')
                # Auto-cleanup on disconnect/failure
                if state in ('failed', 'closed'):
                    await self.cleanup_peer(client_id)

        @pc.on('iceconnectionstatechange')
        async def on_iceconnectionstatechange():
            if client_id in self.PCMap:
                state = self.PCMap[client_id].iceConnectionState
                print(f'[{client_id}] iceConnectionState: {state}')
                # Cleanup on ICE failure/disconnect
                if state in ('failed', 'disconnected', 'closed'):
                    await self.cleanup_peer(client_id)

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
                for i in list(self.PCMap.keys()):
                    if i in self.DCMap and self.DCMap[i].readyState == 'open':
                        try:
                            self.DCMap[i].send(f'broadcast: {dc_message}')
                        except Exception as e:
                            print(f"Error sending message to {i}: {e}")
                print(f'[{channel.label}] datachannel_message: {dc_message}')

        # Get fresh relay-subscribed tracks for this viewer
        audio_track, video_track = self.media_manager.get_tracks_for_viewer()

        if audio_track:
            pc.addTrack(audio_track)
        if video_track:
            pc.addTrack(video_track)

        await pc.setRemoteDescription(RTCSessionDescription(
            sdp=payload['sdp'],
            type=payload['type']
        ))
        await pc.setLocalDescription(await pc.createAnswer())
        await websocket.send(self.encode_msg('SDP_ANSWER', pc.localDescription, client_id))
        print(f"[{client_id}] SDP answer sent. Active viewers: {len(self.PCMap)}")

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
                    print(f'Channel: {self.channel_arn}')
                    print(f'Region: {self.region}')
                    async for message in websocket:
                        msg_type, payload, client_id = self.decode_msg(message)
                        if msg_type == 'SDP_OFFER':
                            await self.handle_sdp_offer(payload, client_id, websocket)
                        elif msg_type == 'ICE_CANDIDATE':
                            await self.handle_ice_candidate(payload, client_id)
            except websockets.ConnectionClosed:
                print('Connection closed, reconnecting...')
                # Clean up all peers on disconnect
                for cid in list(self.PCMap.keys()):
                    await self.cleanup_peer(cid)
                wss_url = self.create_wss_url()
                continue
            except Exception as e:
                print(f'Signaling error: {e}, reconnecting in 3s...')
                await asyncio.sleep(3)
                for cid in list(self.PCMap.keys()):
                    await self.cleanup_peer(cid)
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
                timeout=(10, 20)
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
    parser.add_argument('--use-device-certs', action='store_true', help='Use system certificates')
    parser.add_argument('--width', type=str, default='640', help='Video width (default: 640)')
    parser.add_argument('--height', type=str, default='480', help='Video height (default: 480)')
    parser.add_argument('--framerate', type=str, default='15', help='Video framerate (default: 15)')
    args = parser.parse_args()

    if not AWS_DEFAULT_REGION:
        raise Exception("AWS_DEFAULT_REGION environment variable should be configured.\ni.e. export AWS_DEFAULT_REGION=us-west-2")

    if args.use_device_certs:
        provider = IoTCredentialProvider(
            endpoint=IOT_CREDENTIAL_PROVIDER,
            region=AWS_DEFAULT_REGION,
            thing_name=THING_NAME,
            role_alias=ROLE_ALIAS,
            cert_path=CERT_FILE,
            key_path=KEY_FILE,
            root_ca_path=ROOT_CA
        )
        credentials = provider.get_temporary_credentials()
        if not credentials:
            raise Exception("Failed to obtain temporary credentials")
    else:
        credentials = None

    client = KinesisVideoClient(
        client_id="MASTER",
        region=AWS_DEFAULT_REGION,
        channel_arn=args.channel_arn,
        credentials=credentials,
        file_path=args.file_path,
        video_width=args.width,
        video_height=args.height,
        framerate=args.framerate
    )

    await run_client(client)

if __name__ == '__main__':
    asyncio.run(main())
