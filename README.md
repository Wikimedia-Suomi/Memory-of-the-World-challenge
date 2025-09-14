# Memory-of-the-World-challenge

Points calculation for the Memory of the World challenge in Wikipedia.

## Utilities

`load_participants.py` uses [Pywikibot](https://www.mediawiki.org/wiki/Manual:Pywikibot) to
retrieve usernames listed on the challenge participants page.  By
default it prints the usernames, but an output file can be specified.

```
python load_participants.py
python load_participants.py --output participants.txt
```

Use the `--login` option if the page requires authentication.
