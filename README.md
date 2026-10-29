# UK Group Tree

Give it a list of UK companies and it works out which corporate family each one belongs to, using the "persons with significant control" (PSC) records at Companies House.

For each company it follows the controlling shareholder upwards (opco → midco → topco) until it reaches the top: an individual, a foreign parent, or nobody registered. Companies are then grouped by their ultimate owner. That includes owners recorded under slightly different names ("Mr Andreas Oulie" and "Mr Andreas Søtvedt Oulie") and owners that sit behind several separate UK holding companies.

I built this because when I was running my [funding radar](https://github.com/sanjayashokbuilds/uk-funding-radar), half the "companies" it flagged were layers of the same fund or group structure. If you're trying to keep a CRM clean, that's the same problem: five accounts that are really one customer.

## Run it

```
pip install -r requirements.txt
export COMPANIES_HOUSE_API_KEY=your_key
python -m grouptree --input sample_input.csv --out output
```

The input CSV needs a `company_number` or `company_name` column. Names get matched with Companies House search, and anything that isn't an exact match is marked in the `note` column.

You get two files:

- `output/families.csv`: one row per company, with immediate parent, ultimate UK parent, what sits above that (person, foreign company, etc.), the full chain and any flags
- `output/families.md`: the families written out as trees, biggest first

`sample_input.csv` is the 48 holding companies from one week of my funding radar.

## How it decides the parent

- Only active PSCs count (ceased ones are ignored)
- The strongest control wins: 75–100% of shares, then over 50%, then the right to appoint directors, then 25–50%
- On a tie, a corporate PSC wins over a person, because that's the link that carries the chain on
- A corporate PSC only continues the chain if it's registered in the UK and has a usable company number. Otherwise it's recorded as the top of the chain

## Limits

- PSC records are self-reported and the identification fields are free text, so some parents can't be matched to a number. These are flagged rather than guessed
- It only walks upwards. Finding all the subsidiaries of a parent needs the bulk PSC snapshot, which is next on the list
- Overseas parents are named but not followed any further
- People are matched on first name, surname and country, so two different people with the same name in the same country would be merged. Merged names are listed in the output so you can check them
- Companies House allows 600 requests per 5 minutes, so it runs at about 2 calls a second

## Tests

```
pip install pytest
python -m pytest
```

The tests use a fake Companies House so they run offline.

Sanjay Ashok
