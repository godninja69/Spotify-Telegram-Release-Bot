import os
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
from dotenv import load_dotenv

load_dotenv()

class SpotifyEngine:
    def __init__(self):
        # Uses Client Credentials flow (no user login required, just keys)
        auth_manager = SpotifyClientCredentials(
            client_id=os.getenv("SPOTIFY_CLIENT_ID"),
            client_secret=os.getenv("SPOTIFY_CLIENT_SECRET")
        )
        self.sp = spotipy.Spotify(auth_manager=auth_manager)

    def get_artist_info(self, query):
        """Fetches artist details from a link or name."""
        try:
            if "spotify.com/artist/" in query or "spotify:artist:" in query:
                artist = self.sp.artist(query)
            else:
                results = self.sp.search(q='artist:' + query, type='artist', limit=1)
                if not results['artists']['items']:
                    return None
                artist = results['artists']['items'][0]
            
            return {
                'id': artist['id'],
                'name': artist['name'],
                'url': artist['external_urls']['spotify']
            }
        except Exception as e:
            print(f"Spotify API Error: {e}")
            return None

    def get_latest_releases(self, artist_id):
        """Fetches albums, singles, and features for an artist."""
        releases = []
        try:
            # Crucial: include_groups='album,single,appears_on' ensures we catch features
            results = self.sp.artist_albums(artist_id, include_groups='album,single,appears_on', limit=50)
            
            for item in results['items']:
                releases.append({
                    'id': item['id'],
                    'name': item['name'],
                    'type': item['album_type'],
                    'url': item['external_urls']['spotify'],
                    'image': item['images'][0]['url'] if item['images'] else None,
                    'release_date': item['release_date']
                })
        except Exception as e:
            print(f"Error fetching releases for {artist_id}: {e}")
            
        return releases