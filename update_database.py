import gspread
import json
import os
from beem.amount import Amount
from beem.comment import Comment
from beem.vote import Vote
from datetime import datetime, date
from dateutil.parser import parse
from oauth2client.service_account import ServiceAccountCredentials
from pymongo import MongoClient


CLIENT = MongoClient()
DB = CLIENT.utempian

DIR_PATH = os.path.dirname(os.path.realpath(__file__))
SCOPE = ["https://spreadsheets.google.com/feeds",
         "https://www.googleapis.com/auth/drive"]
CREDENTIALS = ServiceAccountCredentials.from_json_keyfile_name(
    f"{DIR_PATH}/client_secret.json", SCOPE)
GSPREAD_CLIENT = gspread.authorize(CREDENTIALS)
SHEET = GSPREAD_CLIENT.open("Utopian Reviews")


def contribution(row, status):
    """
    Convert row to dictionary, only selecting values we want.
    """
    # Check if contribution was staff picked
    if row[6] == "Yes":
        staff_picked = True
    else:
        staff_picked = False

    # Try and get date, since some people don't enter it correctly
    try:
        review_date = parse(row[1])
    except Exception:
        review_date = datetime(1970, 1, 1)

    url = row[2]

    total_payout = 0
    try:
        comment = Comment(url)
    except Exception:
        return
    # Calculate total (pending) payout of contribution
    if (datetime.now() - review_date).days > 7:
        total_payout = Amount(comment.json()["total_payout_value"]).amount
    else:
        total_payout = Amount(comment.json()["pending_payout_value"]).amount

    # Get votes and comments
    votes = comment.json()["net_votes"]
    comments = comment.json()["children"]

    # Get the author by splitting
    author = url.split("/")[4][1:]

    # Add status for unvoted and pending
    if row[9] == "Unvoted":
        status = "unvoted"
    elif row[9] == "Pending":
        status = "pending"

    # Check if contribution was voted on
    if row[9] == "Yes":
        voted_on = True
        try:
            utopian_vote = Vote(f"{comment.authorperm}|utopian-io").sbd
        except Exception:
            voted_on = False
            utopian_vote = 0
    else:
        voted_on = False
        utopian_vote = 0

    # Check for when contribution not reviewed
    if row[5] == "":
        score = None
    else:
        score = float(row[5])

    # Create contribution dictionary and return it
    new_contribution = {
        "moderator": row[0].strip(),
        "author": author,
        "review_date": review_date,
        "url": url,
        "repository": row[3],
        "category": row[4],
        "staff_picked": staff_picked,
        "picked_by": row[8],
        "status": status,
        "score": score,
        "voted_on": voted_on,
        "total_payout": total_payout,
        "total_votes": votes,
        "total_comments": comments,
        "utopian_vote": utopian_vote
    }
    return new_contribution


def update_posts():
    """
    Adds all reviewed and unreviewed contributions to the database.
    """
    reviewed = []
    unreviewed = []

    # Iterate over all worksheets in the spreadsheet
    for worksheet in SHEET.worksheets():
        if worksheet.title.startswith("Reviewed"):
            reviewed += worksheet.get_all_values()[1:]
        elif worksheet.title.startswith("Unreviewed"):
            unreviewed += worksheet.get_all_values()[1:]

    # Convert row to dictionary
    reviewed = [contribution(x, "reviewed") for x in reviewed]
    unreviewed = [contribution(x, "unreviewed") for x in unreviewed]

    # Lazy so drop database and replace
    contributions = DB.contributions

    for post in reviewed + unreviewed:
        if post:
            contributions.replace_one({"url": post["url"]}, post, True)


def main():
    update_posts()

if __name__ == '__main__':
    main()
    contributions = DB.contributions
