# Memory-of-the-World-challenge

Points calculation for the Memory of the World challenge in Wikipedia.

## Setup

Create and activate a virtual environment, then install the required
packages:

```
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Utilities

`load_participants.py` uses [Pywikibot](https://www.mediawiki.org/wiki/Manual:Pywikibot) to
retrieve usernames listed on the challenge participants page.  By
default it prints the usernames, but an output file can be specified.
The `--wikis` option queries each user's global account to display the
Wikipedia projects where they have at least one edit. Other Wikimedia
projects are ignored.

```
python load_participants.py
python load_participants.py --wikis
python load_participants.py --wikis --output participants.txt
```

Use the `--login` option if the page requires authentication.
