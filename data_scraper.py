#!/usr/bin/env python

import xml.etree.ElementTree as et
import string
import json
import csv
# import codecs, cStringIO # used in UnicodeCSVWriter
import random
import time
from collections import defaultdict
import urllib



################################################################################



SETTINGS_FILE_PATH = "settings.json" # Where the settings for this scraper and analyzer are stored, relative to the current directory
"""
Explanation of the variables used in the settings:
    MASTER_LEADERBOARD_URL: Where the table of all leaderboards is stored
    NAME_CACHE_PATH: Where the name cache is stored (see SteamIDRetriever below)
    CSV_FILE_PATH: Where the csv file is stored, ready to be easily uploaded to Google Spreadsheets
    RANK_MODE: Outputs ranks if set to "true"; outputs scores if set "false"
    RANK_CUTOFF: How many people to get from each leaderboard; e.g. 20 for the top twenty players from each leaderboard
    INTERNET_COOLDOWN: The amount of time (in seconds; e.g. "2.5" or "10") to wait between each call to steam's website. Can be set to 0, but this is not recommended
"""


################################################################################



# These are the exact names used in MASTER_LEADERBOARD_URL
speed_categories = [
    "SPEEDRUN",
    "SPEEDRUN Bard",
    "SPEEDRUN Monk",
    "SPEEDRUN Aria",
    "SPEEDRUN Bolt",
    "SPEEDRUN Dove",
    "SPEEDRUN Eli",
]

score_categories = [
    "HARDCORE",
    "HARDCORE Bard",
    "HARDCORE Monk",
    "HARDCORE Aria",
    "HARDCORE Bolt",
    "HARDCORE Dove",
    "HARDCORE Eli",
]

speed_categories = map(string.upper, speed_categories)
score_categories = map(string.upper, score_categories)
all_categories = speed_categories + score_categories

def get_page(url):
    """ Returns the raw html text located at the given URL.
    """

    try:
        page_text = urllib.urlopen(url).read()
    except:
        print
        print "*** Error opening url '%s' ***" % url
        print
        page_text = ""
    return page_text

#
# TODO: figure out how to make unicode characters work
#
# class UnicodeCSVWriter:
#     """
#     A CSV writer which will write rows to CSV file "f",
#     which is encoded in the given encoding.

#     Copied directly from https://docs.python.org/2/library/csv.html
#     """

#     def __init__(self, f, dialect=csv.excel, encoding="utf-8", **kwds):
#         # Redirect output to a queue
#         self.queue = cStringIO.StringIO()
#         self.writer = csv.writer(self.queue, dialect=dialect, **kwds)
#         self.stream = f
#         self.encoder = codecs.getincrementalencoder(encoding)()

#     def writerow(self, row):
#         self.writer.writerow([s.encode("utf-8") for s in row])
#         # Fetch UTF-8 output from the queue ...
#         data = self.queue.getvalue()
#         data = data.decode("utf-8")
#         # ... and reencode it into the target encoding
#         data = self.encoder.encode(data)
#         # write to the target stream
#         self.stream.write(data)
#         # empty queue
#         self.queue.truncate(0)

#     def writerows(self, rows):
#         for row in rows:
#             self.writerow(row)

class SteamIDRetriever(object):
    """ This class is used to translate steam ids into in-game names
        Note that throughout this object, steam id's are strings, NOT ints or longs
    """

    def __init__(self, average_delay):
        self.cache = {}
        self.average_delay = float(average_delay)

    def load_cache(self, name_cache_fpath):
        try:
            with open(name_cache_fpath, "r") as in_file:
                self.cache = json.load(in_file)
        except IOError:
            print "No steam id/name cache found."

    def save_cache(self, name_cache_fpath):
        with open(name_cache_fpath, "w") as out_file:
            json.dump(self.cache, out_file)

    def name(self, steam_id):
        """ Call this to figure out a user's name given their steam ID. It will eithe return a cached response or scrape steam
            example: "76561197993869032" -> "pancelor"
        """
        if steam_id not in self.cache.keys():
            print "Scraping steam for user id '%s'..."%steam_id
            name = self.cache[steam_id] = self._scrape_name(steam_id)
        return self.cache[steam_id]

    def _scrape_name(self, steam_id):
        """ Visits the given steam_id's Community page on steam to scrape their in-game name
            ***Waits a random amount of time before accessing the internet. The time should be near self.average_delay seconds
                This is to prevent Steam from blocking my IP address
                (I have no idea if they will or if this countermeasure even works, but it seems like a good idea)
            example: "76561197993869032" -> "pancelor"
        """
        wait_time = random.normalvariate(mu=self.average_delay, sigma=self.average_delay/3.0)
        time.sleep(wait_time)

        html_text = get_page("http://steamcommunity.com/profiles/%s"%steam_id)
        prefix = "<title>Steam Community :: "
        postfix = "</title>"
        start = html_text.index(prefix) + len(prefix)
        end = html_text.index(postfix)
        return html_text[start:end]

def gen_all_leaderboards(url):
    """ Scrapes the xml file that contains the urls of all the leaderboards and generates each leaderboard's name and url
        example emission: "SPEEDRUN Bolt", "http://steamcommunity.com/stats/247080/leaderboards/386877/?xml=1"
    """
    root = et.XML(get_page(url))

    for board in root.findall("leaderboard"):
        name = board.find("name").text.strip()
        url = board.find("url").text.strip()
        yield name.upper(), url

def parse_single_leaderboard(url, is_speedrun_leaderboard, rank_cutoff):
    """ Takes the URL of a single leaderboard (e.g. the aria speedrun leaderboard) and generates the relevant data for the top ranking players
        example emission: "76561197970186393", 3, 78655
        """
    if rank_cutoff == 0: # break early
        return

    root = et.XML(get_page(url))
    entries = root.find("entries")
    for entry in entries.findall("entry")[:rank_cutoff]:
        steam_id = entry.find("steamid").text # must be a string to support JSON encoding
        score = int(entry.find("score").text)
        rank = int(entry.find("rank").text)

        if is_speedrun_leaderboard:
            score = 100000000 - score # Account for the weird file storage format; score is now your time in milliseconds

        yield steam_id, rank, score

def format_milliseconds_as_clock_time(milliseconds):
    minutes, milliseconds = divmod(milliseconds, 60*1000)
    seconds = float(milliseconds) / 1000
    return "%02d:%05.2f"%(minutes, seconds)

def download_data(id_retriever, settings):
    # Each entry in player_table will be a list of the proper length- one slot in the list for each leaderboard, in the order implicitly prescribed by the order of the all_categories list
    player_table = defaultdict(lambda: [""]*len(all_categories))

    print "Downloading leaderboards from '%s'..."%settings["MASTER_LEADERBOARD_URL"]
    all_board_urls = [
        (name, board_url)
        for name, board_url in gen_all_leaderboards(settings["MASTER_LEADERBOARD_URL"])
        if name in all_categories
    ]

    for name, board_url in all_board_urls:
        is_speedrun_leaderboard = (name in speed_categories)
        board_index = all_categories.index(name)

        print "Downloading leaderboard '%s'...\n(url='%s')"%(name, board_url)
        for steam_id, rank, score in parse_single_leaderboard(board_url, is_speedrun_leaderboard, settings["RANK_CUTOFF"]):
            steam_name = id_retriever.name(steam_id)
            player_table[steam_name][board_index] = str(rank) if settings["RANK_MODE"] else str(score)
            if is_speedrun_leaderboard:
                time = format_milliseconds_as_clock_time(score)
                print "\t%d: %s with time %s"%(rank, steam_name, time)
            else:
                print "\t%d: %s with score %d"%(rank, steam_name, score)

    return player_table


def main():
    ### Load scraper settings:
    print "Loading settings from '%s'..."%SETTINGS_FILE_PATH
    with open(SETTINGS_FILE_PATH, "r") as in_file:
        settings = json.load(in_file)
    settings["RANK_CUTOFF"] = int(settings["RANK_CUTOFF"])
    settings["INTERNET_COOLDOWN"] = float(settings["INTERNET_COOLDOWN"])
    assert settings["RANK_MODE"].lower() in ["true", "false"], "Bad value in settings: RANK_MODE"
    settings["RANK_MODE"] = (settings["RANK_MODE"].lower() == "true")

    ### Load the name cache
    print "Loading the name cache from '%s'..."%settings["NAME_CACHE_PATH"]
    id_retriever = SteamIDRetriever(settings["INTERNET_COOLDOWN"])
    id_retriever.load_cache(settings["NAME_CACHE_PATH"])

    try:
        player_table = download_data(id_retriever, settings)
        print "Data downloaded successfully!"
    finally:
        ### Save the name cache, even if errors occurred (we don't want to lose all of that data)
        print "Saving the name cache to '%s'..."%settings["NAME_CACHE_PATH"]
        id_retriever.save_cache(settings["NAME_CACHE_PATH"])

    ### Save the rankings to a CSV file
    print "Saving rankings to '%s'..."%settings["CSV_FILE_PATH"]
    with open(settings["CSV_FILE_PATH"], "w") as out_file:
        write = csv.writer(out_file, lineterminator='\n').writerow
        for name, scores in player_table.items():
            row = [name] + scores
            try:
                write(row)
            except UnicodeEncodeError as e:
                stars = "*"*80
                err = "UNICODE ERROR; please search for '\\u' in the name cache (%s) and remove the unicode characters"%(settings["NAME_CACHE_PATH"])
                print "\n".join(["", stars, err, "", str(e), stars, ""])


if __name__ == '__main__':
    main()
