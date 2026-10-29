# Annual Giving Appeals: Channel & Segment Effectiveness (Synthetic Data)

A fake donor database for a small annual giving program, built to answer two questions:

1. Which appeals, channels, and segments give the best return?
2. Which donors are most likely to give again?

This is part 1 of a three-part project. See the [main README](../README.md) for the full project.

It covers five fiscal years (FY2022–FY2026, July 1 – June 30) and about 950–1,000 donors a year. All data is synthetic. Run `generate_data.py` to recreate it exactly (fixed seed).

```
python generate_data.py
```

Run it from the main project folder. It saves the CSVs to the `data/` folder.

## How it works

The script sets **inputs** (how likely someone is to respond, how big their gift is, what each appeal costs) and lets the **outputs** (ROI, retention, segment performance) come out of the simulation. Inputs are tied to published benchmarks where one exists. The rest are marked `# Assumption` in the code.

A few rules drive most of the results:

- **Response depends on donor status**, set at the start of each fiscal year: Repeat, New, Lapsed, or Never. Donors with larger usual gifts respond somewhat more often.
- **Gift size follows each donor's history.** Their usual gift leans toward their most recent gift and drifts a little each year.
- **Timing matters.** Year-end and fiscal year-end appeals get stronger response; fall and spring are weaker. Unsolicited gifts peak in November and December.
- **Contact info decays.** Returned mail, bounced emails, and unsubscribes remove contact info over time.
- **Tribute donors** (gifts in memory, in honor, or to a friend's personal fundraiser) are flagged `tribute_only` and rarely give again.
- **Second gifts usually come the following year.** Because status is set at the start of the fiscal year, a donor who gives for the first time partway through a year keeps the status they started the year with (usually Never) until the next fiscal year begins. Most second gifts therefore arrive with the next year's appeals, often 12–18 months after the first gift. This timing comes from the simulation's rules, not from real donor behavior.

### Giving levels

Based on a donor's **total** giving in one fiscal year:

| Total in a year | Level | Effect |
|---|---|---|
| Under $500 | Annual giving | Mass appeals only |
| $500–$1,000 | Leadership | Mass appeals plus personal outreach for the next two years |
| Over $1,000 | Mid-level | Moves to the mid-level team the next year and leaves this dataset |

Transferred donors stay in the files, marked "Transferred to Mid-Level," so they aren't counted as lapsed.

### Funds

Each gift goes to one of three funds: **Annual Fund (Unrestricted)**, **Program Fund**, or **Restricted Fund**. Larger donors are modestly more likely to restrict. Most later gifts (75%) go back to the donor's first fund. In-memory gifts usually (60%) go to the Restricted Fund; there's no separate tribute fund.

## Appeal calendar

Each fiscal year has 15 appeals plus one catch-all **General Annual Giving** appeal (`FYxx-GEN`) for unsolicited gifts.

| Timing | Direct mail | Email | Personal outreach | Social media |
|---|---|---|---|---|
| Fall | Current | Current, Lapsed | Leadership (current) | |
| GivingTuesday | | All groups | | Posts |
| Calendar year-end | All groups | All groups | | Posts |
| Spring | Current | Current, Lapsed | Leadership (not yet renewed, lapsed) | |
| Fiscal year-end | All groups | All groups | | Posts |

Plus a fall **acquisition mailing** to an 18,000-name rented list.

### Segments

| Channel | Segments |
|---|---|
| Direct mail | Current (by last gift: Under $100, $100–$499, $500–$1,000); Lapsed 1 Yr (Under $100, $100+); Lapsed 2–4 Yrs; Never Donors (on file under 3 years) |
| Email | Current Donors, Lapsed Donors, Never Donors |
| Personal outreach | Leadership - Current, Leadership - Lapsed |
| Social media | General Public |
| Acquisition | Acquisition (Rented List) |

## Files

```
donors.csv ──< solicitations.csv >── appeals.csv ──< appeal_segments.csv
   │   │                                  │
   │   └──────────< gifts.csv >───────────┘
   │
   └──< donor_fy_summary.csv
```

All files are in the `data/` folder.

| File | One row per |
|---|---|
| `donors.csv` | Person (donor or non-donor), with giving history before FY2022 |
| `appeals.csv` | Appeal, with total audience and costs |
| `appeal_segments.csv` | Segment within an appeal, with its audience and costs (sums to `appeals.csv`) |
| `solicitations.csv` | Person asked in an appeal, responders and non-responders |
| `gifts.csv` | Gift |
| `donor_fy_summary.csv` | Person per fiscal year, including years with no gift |
| `benchmark_check.csv` | Simulated results vs. published benchmarks |

### Columns worth noting

- **`gifts.gift_date` vs. `date_received`**: checks arriving January 1–6 are credited to December 31 (postmark date). `date_received` keeps the actual arrival date.
- **`gifts.appeal_id`**: every gift has one. Unsolicited gifts are credited to `FYxx-GEN`.
- **`solicitations.csv`**: no "responded" column. Join to `gifts.csv` on `donor_id` and `appeal_id`. Acquisition and social media have no rows (rented names and social viewers aren't in the database).
- **`solicitations.bad_contact_info`**: returned mail, bounced email, or wrong number. The contact info is then removed in `donors.csv`.
- **`donors.csv` contact fields and solicit codes** reflect the record at the end of FY2026.
- **`donors.one_solicitation_per_year`**: the donor only gets the first appeal they qualify for each year.
- **`donor_fy_summary.donor_status_fy`**: New, Retained, Reactivated, Lapsed, Non-donor, or Transferred to Mid-Level.
- **`*_as_of_fy_end` columns** use only information known by the end of that year, so they're safe as model inputs.

## Calculated summary fields

Some fields aren't raw records. They're **calculated summary fields**: values that summarize many records (gifts, events, segments) into one number stored on a record. CRMs store the same kind of field. Raiser's Edge calls them **smart fields**, and Salesforce calls them **rollup fields**, for things like a donor's last gift date or lifetime giving. They come in two kinds:

- **Calculated from data in this dataset.** You can recompute these yourself from the other files, which is a good way to check your joins.
- **Calculated from data not included.** These summarize history from before FY2022, or events, whose underlying records aren't in the dataset. Use them as given.

Each field also reflects a specific point in time, shown in the "As of" column. Only fields as of the start or end of a given year are safe to use as model inputs for that year.

| File | Field | Summarizes | As of | Recompute from this dataset? |
|---|---|---|---|---|
| donors.csv | `prior_gift_count_pre_fy2022`, `prior_gift_amount_pre_fy2022` | All gifts before FY2022 | End of FY2021 | No |
| donors.csv | `last_gift_fy_pre_fy2022`, `last_gift_amount_pre_fy2022` | Most recent gift before FY2022 | End of FY2021 | No |
| donors.csv | `first_gift_fy`, `first_gift_type` | Donor's first-ever gift | First gift | Only if the first gift was in FY2022 or later |
| donors.csv | `tribute_only` | Whether all of a donor's gifts are tribute gifts | End of FY2026 | Partly (needs pre-FY2022 history) |
| donors.csv | `events_attended` | Lifetime event attendance | End of FY2026 | No (event records not included) |
| donors.csv | `mid_level_transfer_fy` | Yearly giving totals: the year after a total first passed $1,000 | End of FY2026 | Yes, from gifts.csv |
| appeals.csv | `audience_size`, `hard_cost`, `staff_hours`, `staff_cost`, `total_cost`, `number_of_segments`, `segment_groups_targeted` | The appeal's segments | Appeal | Yes, from appeal_segments.csv |
| solicitations.csv | `donor_status_at_fy_start`, `tribute_only` | Donor's giving history | Start of the fiscal year | Partly (needs pre-FY2022 history) |
| donor_fy_summary.csv | `gave_this_fy`, `fy_gift_count`, `fy_gift_amount`, `giving_level_fy` | That year's gifts | End of each fiscal year | Yes, from gifts.csv |
| donor_fy_summary.csv | `donor_status_fy` | That year's and earlier giving | End of each fiscal year | Partly (FY2022 needs pre-FY2022 history) |
| donor_fy_summary.csv | `lifetime_gift_count_as_of_fy_end`, `lifetime_gift_amount_as_of_fy_end` | Pre-FY2022 totals + gifts through that year | End of each fiscal year | Partly (starts from pre-FY2022 totals) |
| donor_fy_summary.csv | `tribute_only_as_of_fy_end`, `events_attended_as_of_fy_end` | Same as the donors.csv versions, by year | End of each fiscal year | Partly |

Giving before FY2022 is available only as these summaries, so you can't tell *which* years a donor gave between their first and last gift. Year-by-year patterns, such as consecutive years of giving, can only be measured from FY2022 on.

A few other fields are simple calculations from a single value on the same row, not summaries: `age_group` (from `birth_year`), `fiscal_year` (from `gift_date`), `fund_category` (from `fund`), `staff_cost` (`staff_hours` × $40), and `total_cost` (`hard_cost` + `staff_cost`).

In a real CRM, all of these would be smart fields or roll-up fields. The difference here is only whether the records behind them are included in this extract.

## Key inputs

| Input | Value | Basis |
|---|---|---|
| Direct mail response | Repeat 21%, New 9%, Lapsed 2.8%, Never 0.6% | Tuned to ANA response and FEP retention |
| Email response | Repeat 1.5%, New 0.8%, Lapsed 0.15%, Never 0.06% | M+R, raised for a smaller organization |
| Personal outreach response (if reached) | Repeat 45%, New 30%, Lapsed 12% | Assumption |
| Acquisition response | 1% | Assumption |
| Mail cost | $0.60–$0.75 per piece plus creative | Industry example |
| Staff time | $40/hour | Assumption |
| Tribute donor response | 22% of a standard donor's | Tuned to single-digit retention (Bloomerang) |

Personal outreach, social media, tribute, and never-donor results rest on the least certain inputs.

## Benchmark check

| Metric | Simulated | Benchmark | Source |
|---|---|---|---|
| Direct mail response, existing donors | 9.3% | 5%–9% | ANA 2024 |
| Cost to raise $1, mail to existing donors | $0.15 | $0.20–$0.25 | Greenfield |
| Cost to raise $1, acquisition | $1.07 | $1.00–$1.50 | Greenfield |
| Email response rate | 0.28% | 0.05% | M+R 2026 |
| Email revenue per 1,000 sent | $348 | $54 | M+R 2026 |
| Email addresses lost to bounces per year | 3.3% | 4% | M+R 2026 |
| Donor retention, overall | 40.4% | 43.3% | FEP Q4 2025 |
| Donor retention, new | 18.8% | 18.9% | FEP Q4 2025 |
| Donor retention, repeat | 59.8% | 59.3% | FEP Q4 2025 |
| Retention, new tribute donors | 3.8% | Single digits | Bloomerang |

Email runs well above M+R on purpose. M+R reflects large national lists, and a small organization's email list is closer to its donors. Retention excludes donors who moved to mid-level.

## Analysis tips

- **Compare channels within the same segment group.** Mail to current donors will always beat email to never donors.
- **Measure ROI two ways:** revenue ÷ hard cost and revenue ÷ total cost. Personal outreach is mostly staff time.
- **Watch for selection effects.** Personal outreach goes to the best donors, so it looks good partly because of who it reaches.
- **Track mid-level transfers alongside revenue.** Top donors leave each year, so revenue can dip while the program is working.
- **Separate out `FYxx-GEN`** when comparing appeals. It has no cost and no audience.
- **Treat time-to-second-gift results as a feature of this dataset.** The 12–18 month gap before most second gifts is built in by the rule above. The approach (measuring time between first and second gifts on equal follow-up time) carries over to real data; the specific timing does not.
- **For fund choice,** look at standard gifts separately, since in-memory gifts lean restricted.
- **For a give-again model,** use `donor_fy_summary` (everyone who has ever given), with whether they gave the next year as the target. Train on FY2022→2023 through FY2024→2025, test on FY2025→2026, and drop donors after they move to mid-level.

## Sources

ANA 2024 Response Rate Report · M+R Benchmarks 2026 · Fundraising Effectiveness Project (Q3 and Q4 2025 reports) · Bloomerang, *Memorial and Tribute Donors Can Be Retained* · Greenfield, *Fund-Raising: Evaluating and Managing the Fund Development Process* (1999)
