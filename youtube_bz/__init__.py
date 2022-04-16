import argparse
import aiohttp
import asyncio
import Levenshtein
import ujson
import youtube_dl
import re
import os


class MyLogger(object):
    def debug(self, msg):
        pass

    def warning(self, msg):
        pass

    def error(self, msg):
        print(msg)


def my_hook(d):
    if d['status'] == 'finished':
        pass


ydl_opts = {
    'format': 'bestaudio/best',
    'postprocessors': [{
        'key': 'FFmpegExtractAudio',
    }],
    'logger': MyLogger(),
    'progress_hooks': [my_hook],
}


def download(title, video_id):
    print('[Downloading] {} : {}'.format(title, video_id))
    ydl_opts['outtmpl'] = os.path.join('.', '{}.%(ext)s'.format(title))
    with youtube_dl.YoutubeDL(ydl_opts) as ydl:
        ydl.download([video_id])
    print('[Downloaded] {}'.format(title))


async def get_best_match(yt_initial_data, track):
    best_distance = None
    best_match = None
    for itemSectionRenderer in yt_initial_data['contents']['twoColumnSearchResultsRenderer']['primaryContents']['sectionListRenderer']['contents'][0]['itemSectionRenderer']['contents']:
        if 'videoRenderer' in itemSectionRenderer:
            video = {'title': itemSectionRenderer['videoRenderer']['title']['runs'][0]['text'], 'id': itemSectionRenderer['videoRenderer']['videoId']}
            distance = Levenshtein.distance(track['title'].lower(), video['title'].lower())
            if best_distance is None:
                best_distance = distance
                best_match = video
            if distance < best_distance:
                best_distance = distance
                best_match = video
    return best_match


async def get_yt_intital_data(search_results):
    regex = r'(var\ ytInitialData\ =\ )(.*);</script><script'
    yt_initial_data = re.search(regex, search_results).group(2)
    return ujson.loads(yt_initial_data)


async def get_search_query(release, track):
    search_query = f'"{release["artist-credit"][0]["name"]}" "{release["title"]}" "{track["title"]}" "Auto-generated"'
    return search_query


async def get_yt_search_results(search_query):
    async with aiohttp.ClientSession("https://www.youtube.com") as session:
        async with session.get('/results', params={'search_query': search_query}) as response:
            search_results = await response.text()
            return search_results


async def get_musicbrainz_release(mbid):
    async with aiohttp.ClientSession('https://musicbrainz.org') as session:
        async with session.get(f'/ws/2/release/{mbid}', params={'inc': 'artists+recordings', 'fmt': 'json'}) as response:
            html = await response.text()
            return ujson.loads(html)


async def chain_call(release, track):
    search_query = await get_search_query(release, track)
    yt_search_results = await get_yt_search_results(search_query)
    yt_initial_data = await get_yt_intital_data(yt_search_results)
    best_match = await get_best_match(yt_initial_data, track)
    return best_match


async def run(mbid):
    release = await get_musicbrainz_release(mbid)
    tasks = [chain_call(release, track) for track in release['media'][0]['tracks']]
    results = await asyncio.gather(*tasks)
    print(results)

    # Run download in thread pool to avoid blocking IO
    for result in results:
        loop = asyncio.get_running_loop()
        loop.run_in_executor(None, download, result['title'], result['id'])


def main():
    parser = argparse.ArgumentParser(description="Find and download Youtube Videos associated to an Album on MusicBrainz.")
    parser.add_argument('mbid', help="music brainz identifer of a release")
    args = parser.parse_args()
    loop = asyncio.get_event_loop()
    loop.run_until_complete(run(args.mbid))
