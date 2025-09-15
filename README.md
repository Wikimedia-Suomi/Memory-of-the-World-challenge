# Memory-of-the-World-challenge

Points calculation for the Memory of the World challenge in Wikipedia. 
* Link to the stats page: [Memory of the World challenge 2025/Participants/Results](https://meta.wikimedia.org/wiki/Memory_of_the_World_challenge_2025/Participants/Results)

## Points calculation rules

This is an unofficial automatic points calculation page. Please check the points and add your results to the main page manually.

### Wikidata labels

Each new language label added to a UNESCO Memory of the World item earns 1 point. Adding labels is detected from Wikidata's automatic edit summaries. There may be missing points due to missing summary formats in the code. Please notify on the talk page if there are missing summaries.

### UNESCO links in articles

- **Adding a link to an existing article:** 2 points
  – Checks if the user has added a link to <https://www.unesco.org/en/memory-world>

- **Creating a new article with the link:** 5 points
  – Checks if the user has added a link to <https://www.unesco.org/en/memory-world> and created the article between 2025-09-01 and 2025-09-30

- **Creating a list article with the link:** 25 points
  – Checks if the user has added a link to <https://www.unesco.org/en/memory-world>, created the article between 2025-09-01 and 2025-09-30, and the Wikidata P31 value is Q13406463 (Wikimedia list article)

If an edit is reverted, it is ignored. Reversion is detected using change tags. Only edits made between 2025-09-01 and 2025-09-30 are counted.

## Setup

Create and activate a virtual environment, then install the required
packages:

```
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
```

Create a `user-config.py` file so Pywikibot can log in to the Wikimedia
projects.


## Updating statistics

To refresh the set of participant wikis and publish updated statistics:

```bash
python manage.py load_participants --wikis
python manage.py check_unesco_edits
```

Run `check_unesco_edits` with `--dry-run` to display the results locally
without writing them to the wiki:

```bash
python manage.py check_unesco_edits --dry-run
```
