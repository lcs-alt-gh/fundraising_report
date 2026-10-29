"""
Synthetic Annual Giving dataset: appeal channel effectiveness

A fake donor database for an annual giving program. Mass appeals (direct mail,
email, social media) go to segments of current, lapsed, and never donors, and a
small personal-outreach program goes to leadership-level donors within annual giving.
Five fiscal years: FY2022-FY2026 (July 1 - June 30).

Design rule: the INPUTS below describe basic donor behavior and costs, tied
to published benchmarks where one exists. The OUTPUTS (ROI, retention,
segment and channel performance) are NOT set anywhere; they come out of the
simulation. Every input without a benchmark is marked as an assumption.

Constituents coded Do Not Contact or Do Not Solicit are assumed to have
already been removed from this extract.
"""

import numpy as np
import pandas as pd
from datetime import date, timedelta
import os

SEED = 3  # chosen from seeds that meet the realism rule that every appeal gets at least one gift
rng = np.random.default_rng(SEED)


# PARAMETERS

START_FY, END_FY = 2022, 2026
BASE = START_FY - 1          # giving history before the dataset runs through the end of this FY
N_ON_FILE = 6000            # roughly based on a smaller shop, roughly 900-1,000 donors a year
STAFF_HOURLY_RATE = 40       # estimated cost of one staff hour

START_STATUS_MIX = {"Repeat": 0.16, "New": 0.05, "Lapsed": 0.30, "Never": 0.49}  # Assumption

# Where records come from
SOURCE_MIX_PAST_DONORS = {"Acquisition Mailing": 0.28, "Event Attendee": 0.18, "Website Signup": 0.12,
                          "Paid List": 0.07, "Manually Added": 0.10, "Unknown": 0.25}
SOURCE_MIX_NON_DONORS = {"Paid List": 0.30, "Event Attendee": 0.22, "Website Signup": 0.18,
                         "Manually Added": 0.10, "Unknown": 0.20}
NEW_NON_DONOR_RECORDS_PER_YEAR = {"Paid List": (225, 375), "Event Attendee": (90, 150),
                                  "Website Signup": (60, 120), "Manually Added": (15, 38)}

# Contact info: chance it's on file, by source, then decays with time
# address, email, phone on file when the record is created
CONTACT_AT_CREATION = {
    "Acquisition Mailing": (1.00, 0.35, 0.45), "Paid List": (1.00, 0.30, 0.50),
    "Event Attendee": (0.60, 0.90, 0.50), "Website Signup": (0.35, 1.00, 0.20),
    "Manually Added": (0.85, 0.60, 0.60), "Unknown": (0.90, 0.55, 0.60),
    "Social Media": (0.90, 1.00, 0.30),        # gave through the organization's own donation page
    "Unsolicited Gift": (0.80, 0.70, 0.40), "Tribute Gift": (0.85, 0.55, 0.30),
    "Personal Fundraiser": (0.30, 0.50, 0.10),  # peer-to-peer platforms pass along little contact info
}
YEARLY_CONTACT_SURVIVAL = {"address": 0.975, "email": 0.94, "phone": 0.95}  # per year without contact
EMAIL_AGE_FACTOR = {"Under 40": 1.10, "40-64": 1.00, "65+": 0.80}

# Solicit codes. Assumption: Most specific requests come from donors; only donors ask for one solicitation a year. Email requests outnumber call requests.
SOLICIT_CODE_RATES = {
    "Non-donor": {"do_not_mail": 0.01, "do_not_call": 0.02, "do_not_email": 0.03,
                  "one_solicitation_per_year": 0.00},
    "Donor":     {"do_not_mail": 0.05, "do_not_call": 0.08, "do_not_email": 0.14,
                  "one_solicitation_per_year": 0.10},
}

# Contact info lost during the five years
BAD_ADDRESS_RATE = {"Current": 0.02, "Other": 0.06}  # Assumption: returned mail, NCOA updates
EMAIL_BOUNCE_PER_SEND = 0.01      # M+R Benchmarks 2026: 4% of subscribers lost to bounces per year
EMAIL_UNSUB_PER_SEND = 0.0024     # M+R Benchmarks 2026: 12% unsubscribe over ~50 emails/yr = ~0.24% per email
WRONG_NUMBER_RATE = 0.08          # Assumption

# Response: chance a solicited person gives to 1 appeal
# Status at the start of the fiscal year: Repeat = gave last FY and before;
# New = first-ever gift was last FY; Lapsed = gave before but not last FY;
# Never = has never given. Direct mail rates are set so donor-file mailings land near the 5-9% range in the ANA 2024 Response Rate Report
# Retention lands near the FEP Q4 2025 Report.
# Email starts from M+R Benchmarks 2026 (0.05% response, $54 per 1,000) and is raised for a smaller organization.
# Checked in benchmark_check.csv

RESPONSE = {
    "Direct Mail":       {"Repeat": 0.21,  "New": 0.09,  "Lapsed": 0.028,  "Never": 0.006},
    "Email":             {"Repeat": 0.015, "New": 0.008, "Lapsed": 0.0015, "Never": 0.0006},
    "Personal Outreach": {"Repeat": 0.45,  "New": 0.30,  "Lapsed": 0.12},
}
# Larger donors are somewhat more loyal. Informed by an older Bloomerang webinar citing
# FEP data: first-time donors giving under $100 retained at 21% vs 29% for all first-time donors.
GIFT_LEVEL_RESPONSE_MULT = {"Under $100": 0.80, "$100-$499": 1.20, "$500-$1,000": 1.40, "Over $1,000": 1.40}  # informed by Bloomerang/FEP

# Seasonality: people give most around the holidays, and offices push hardest at the end of the fiscal year. Applies to mail and email response.
TIMING_RESPONSE_MULT = {  # Assumption
    "Direct Mail": {"FALL": 0.6, "YE": 1.6, "SPR": 0.7, "FYE": 1.3},
    "Email":       {"FALL": 0.9, "GT": 1.6, "YE": 1.4, "SPR": 0.9, "FYE": 1.6},  # milder dip: email is cheap to send and still nets a few gifts; GivingTuesday and fiscal year-end are the big online pushes
}
# When unsolicited gifts arrive by calendar month. Donors think about GivingTuesday, the December holidays, and giving before the calendar
# year ends, so unsolicited giving peaks in November-December only.
# The fiscal year-end push is the focus of the fundraising office, so June giving is mostly solicited.
UNSOLICITED_MONTH_WEIGHT = {7: 0.7, 8: 0.7, 9: 0.8, 10: 0.9, 11: 1.5, 12: 3.0,
                            1: 0.9, 2: 0.7, 3: 0.8, 4: 0.8, 5: 0.9, 6: 0.9}  # Assumption
ALREADY_GAVE_THIS_FY_MULT = 0.3   # Assumption: a second gift in the same year is less likely
PO_CONNECT_RATE = {"Phone": 0.60, "Personal Email": 0.50}  # Assumption
PO_ASK_MULTIPLIER = 1.25     # Modest ask increase for personal outreach

# Leadership annual giving: the FEP Q3 2025 Report defines mid-level donors as giving $501-$5,000 a year.
# Giving levels, based on TOTAL giving in a single fiscal year:
#   $500-$1,000  = leadership annual giving: mass appeals + personal outreach
#   over $1,000  = mid-level: moved to the mid-level team at the start of the next
#                  fiscal year, and out of annual giving (and out of this dataset)
LEADERSHIP_THRESHOLD = 500
MID_LEVEL_THRESHOLD = 1000
# There is no cap on gift size. A rare large gift simply moves the donor up a level in the next year.

ACQ_LIST_SIZE = 18000
ACQ_RESPONSE = 0.010              # Assumption: about 1% response to a rented list

SOCIAL_CTR = 0.010                # Assumption: link clicks per impression
SOCIAL_PAGE_COMPLETION = 0.12     # Assumption: share of social link clicks that complete a gift
SOCIAL_NEW_DONOR_SHARE = 0.50     # Assumption: share of social media gifts from new donors
GIVINGTUESDAY_REACH_MULT = 3.0    # Assumption: GivingTuesday draws more attention than a regular post

# Assumptions
UNSOLICITED_RATE = {"Repeat": 0.06, "New": 0.03, "Lapsed": 0.01, "Never": 0.002}
UNSOLICITED_NEW_DONORS_PER_YEAR = (60, 105)

# Tribute donors give because of someone they know or to a friend's personal (peer-to-peer) fundraiser. Bloomerang ("Memorial and Tribute Donors
# Can Be Retained"): memorial/tribute donor retention is "typically in the single digits".
TRIBUTE_NEW_DONORS_PER_YEAR = (45, 83)
TRIBUTE_TYPE_MIX = {"In Memory": 0.70, "In Honor": 0.30}
PERSONAL_FUNDRAISER_NEW_DONORS_PER_YEAR = (30, 60)
TRIBUTE_RESPONSE_MULT = 0.22      # set so their retention lands in the single digits
EXISTING_DONOR_TRIBUTE_SHARE = 0.15  # share of existing donors' unsolicited gifts that are tributes

# Events - attendence assumptions:
# Chance of attending at least one organization event in a year, by status
EVENT_ATTENDANCE_RATE = {"Repeat": 0.12, "New": 0.08, "Lapsed": 0.03, "Never": 0.02}
LEADERSHIP_EVENT_MULT = 2.5       # leadership donors attend more events


# Simplified fund categories: Unrestricted, Program (a general area of the work), and Restricted (a specific purpose).
FUNDS = {
    "Unrestricted": {"Annual Fund (Unrestricted)": 1.0},
    "Program":      {"Program Fund": 1.0},
    "Restricted":   {"Restricted Fund": 1.0},
}
# Assumptions:
# Chance a gift goes to each fund category, by the donor's usual gift level.
# Modest link with gift size: an assumption that larger donors restrict gifts somewhat more often. There is no direct link set with how consistently someone gives and the fund.
FUND_CATEGORY_BY_LEVEL = {
    "Under $100":  {"Unrestricted": 0.78, "Program": 0.15, "Restricted": 0.07},
    "$100-$499":   {"Unrestricted": 0.70, "Program": 0.19, "Restricted": 0.11},
    "$500+":       {"Unrestricted": 0.60, "Program": 0.23, "Restricted": 0.17},
}
HOME_FUND_LOYALTY = 0.75   # Assumption: share of a donor's later gifts that go to the fund they first supported


IN_MEMORY_TO_RESTRICTED = 0.60  # Assumption: in-memory gifts usually go to an existing restricted fund

# Gift size: based on each donor's own average past gift
FIRST_GIFT_MEDIAN = {"Direct Mail": 50, "Email": 50, "Personal Outreach": 100, "Unsolicited": 50,
                     "Social Media": 35, "Personal Fundraiser": 35,  # near M+R's $31-$34 average Facebook Fundraiser gift (2019 and 2023 studies)
                     "In Memory": 50, "In Honor": 50}
# Assumptions:
FIRST_GIFT_SPREAD = 1.0
GIFT_TO_GIFT_SPREAD = 0.25
RECENT_GIFT_WEIGHT = 0.6          # a donor's usual gift leans toward their most recent gift
# Each year, donors' usual gift drifts: some upgrade, some downgrade, slightly upward on average (FEP report)
YEARLY_GIFT_DRIFT = (0.05, 0.20)  # lognormal (mean, spread) applied once a year
PRIOR_AVG_GIFT_MEDIAN = 80
PRIOR_AVG_GIFT_SPREAD = 0.85      # wide spread so a realistic share are leadership donors

LAG_DAYS = {"Direct Mail": 18, "Email": 3, "Social Media": 2, "Personal Outreach": 20}
YE_MAIL_LAG_DAYS = 24   # year-end donors send gifts closer to the Christmas, so many checks are mailed in late December
ONLINE_PUSH_LAG_DAYS = 0.7   # GivingTuesday and fiscal year-end online gifts come the same day or within a day or two

# Year-end crediting: checks received in the first days of January (1-6) were postmarked by December 31,
# so they're credited to December 31 (the postmark sets the donor's tax year). date_received keeps the actual arrival date.
YEAR_END_CHECK_CUTOFF_DAY = 6

GIVING_TUESDAY = {2022: date(2021, 11, 30), 2023: date(2022, 11, 29), 2024: date(2023, 11, 28),
                  2025: date(2024, 12, 3), 2026: date(2025, 12, 2)}
FYS = list(range(START_FY, END_FY + 1))


def fiscal_year(d):
    return d.year + 1 if d.month >= 7 else d.year


def fy_start(fy):
    return date(fy - 1, 7, 1)


def fy_end(fy):
    return date(fy, 6, 30)


def age_group(birth_year, as_of=END_FY):
    age = as_of - birth_year
    return "Under 40" if age < 40 else ("40-64" if age < 65 else "65+")


def random_date(start, end):
    return start + timedelta(days=int(rng.integers(0, max((end - start).days, 0) + 1)))


def seasonal_date(start, end):
    """A date between start and end, weighted toward December and June."""
    months = []
    d = date(start.year, start.month, 1)
    while d <= end:
        months.append(d)
        d = date(d.year + (d.month == 12), d.month % 12 + 1, 1)
    w = np.array([UNSOLICITED_MONTH_WEIGHT[m.month] for m in months])
    m = months[rng.choice(len(months), p=w / w.sum())]
    m_end = date(m.year + (m.month == 12), m.month % 12 + 1, 1) - timedelta(days=1)
    return random_date(max(m, start), min(m_end, end))


def pick(mix):
    return rng.choice(list(mix), p=list(mix.values()))


def round_gift(amt):
    if rng.random() < 0.75:  # donors like round numbers most of the time
        step = 5 if amt < 100 else (25 if amt < 1000 else 250)
        amt = max(step, round(amt / step) * step)
    return round(float(max(amt, 5)), 2)


def gift_level(amount):
    if amount > MID_LEVEL_THRESHOLD:
        return "Over $1,000"
    if amount >= LEADERSHIP_THRESHOLD:
        return "$500-$1,000"
    return "$100-$499" if amount >= 100 else "Under $100"


# CONSTITUENT RECORDS
donors = {}
typical_gift, life_count, life_amount = {}, {}, {}
gave_fys, first_fy = {}, {}
std_count = {}        # number of standard (non-tribute) gifts
fy_amount = {}        # donor -> {fiscal year: total given}
last_gift_amt = {}    # donor -> amount of most recent gift
events_by_fy = {}     # donor -> {fiscal year: events attended}
next_num = 1


def apply_donor_codes(d):
    """Once someone becomes a donor, they may ask for donor-type solicit codes."""
    for code, rate in SOLICIT_CODE_RATES["Donor"].items():
        if rng.random() < rate:
            donors[d][code] = 1


def add_event(d, fy, n=1):
    events_by_fy[d][fy] = events_by_fy[d].get(fy, 0) + n


def new_record(created, source, birth_year=None, years_without_contact=0.0):
    """Create a constituent. Contact info depends on source, then decays with time."""
    global next_num
    d = f"D{next_num:05d}"
    next_num += 1
    if birth_year is None:
        birth_year = int(rng.integers(1938, 2002))
    ag = age_group(birth_year)
    addr_p, email_p, phone_p = CONTACT_AT_CREATION[source]
    s = YEARLY_CONTACT_SURVIVAL
    rec = {
        "donor_id": d, "birth_year": birth_year, "age_group": ag,
        "state": rng.choice(["MA", "NH", "RI", "CT", "NY", "ME", "Other"],
                            p=[0.62, 0.08, 0.05, 0.05, 0.07, 0.03, 0.10]),
        "acquisition_source": source, "record_created_date": created,
        "has_mailing_address": int(rng.random() < addr_p * s["address"] ** years_without_contact),
        "has_email": int(rng.random() < email_p * EMAIL_AGE_FACTOR[ag] * s["email"] ** years_without_contact),
        "has_phone": int(rng.random() < phone_p * s["phone"] ** years_without_contact),
    }
    for code, rate in SOLICIT_CODE_RATES["Non-donor"].items():
        rec[code] = int(rng.random() < rate)
    rec.update({"prior_gift_count_pre_fy2022": 0, "prior_gift_amount_pre_fy2022": 0.0,
                "first_gift_fy": None, "first_gift_type": None,
                "last_gift_fy_pre_fy2022": None, "last_gift_amount_pre_fy2022": None})
    donors[d] = rec
    typical_gift[d], life_count[d], life_amount[d] = None, 0, 0.0
    gave_fys[d], first_fy[d], std_count[d] = set(), None, 0
    fy_amount[d], last_gift_amt[d], events_by_fy[d] = {}, None, {}
    if source == "Event Attendee":
        add_event(d, min(fiscal_year(created), START_FY - 1) if created < fy_start(START_FY) else fiscal_year(created))
    return d


# People on file before FY2022 - with giving history
for _ in range(N_ON_FILE):
    status0 = pick(START_STATUS_MIX)
    birth_year = int(rng.integers(1938, 2001))
    earliest_fy = max(2005, birth_year + 22)
    if status0 == "Never":
        created = random_date(date(earliest_fy, 1, 1), date(BASE, 6, 30))
        new_record(created, pick(SOURCE_MIX_NON_DONORS), birth_year,
                   years_without_contact=max(0, BASE - fiscal_year(created)))
        continue
    if status0 == "New":
        first, last, years_given = BASE, BASE, 1
    elif status0 == "Repeat":
        first = int(rng.integers(earliest_fy, BASE)) if earliest_fy < BASE else BASE - 1
        last = BASE
        years_given = int(rng.integers(2, last - first + 2))
    else:  # Lapsed
        first = int(rng.integers(earliest_fy, BASE - 1)) if earliest_fy < BASE - 1 else BASE - 2
        last = int(rng.integers(first, BASE))
        years_given = int(rng.integers(1, last - first + 2))
    created = random_date(date(first - 1, 1, 1), date(first - 1, 12, 31))
    count = years_given + int(rng.poisson(0.3 * years_given))
    # Assumption: many one-time donors were tribute donors who never gave again
    is_trib = count == 1 and rng.random() < (0.40 if status0 == "Lapsed" else 0.25)
    if is_trib:
        first_type = pick({"In Memory": 0.50, "In Honor": 0.20, "Personal Fundraiser": 0.30})
        source = "Personal Fundraiser" if first_type == "Personal Fundraiser" else "Tribute Gift"
    else:
        first_type = "Standard" if rng.random() > 0.05 else pick({"In Memory": 0.7, "In Honor": 0.3})
        source = pick(SOURCE_MIX_PAST_DONORS)
    d = new_record(created, source, birth_year, years_without_contact=BASE - last)
    avg = rng.lognormal(np.log(PRIOR_AVG_GIFT_MEDIAN * (0.6 if is_trib else 1)), PRIOR_AVG_GIFT_SPREAD)
    total = round(avg * count * rng.lognormal(0, 0.1), 2)
    last_amt = round_gift(avg * rng.lognormal(0, GIFT_TO_GIFT_SPREAD))
    donors[d].update({"prior_gift_count_pre_fy2022": count, "prior_gift_amount_pre_fy2022": total,
                      "first_gift_fy": first, "first_gift_type": first_type,
                      "last_gift_fy_pre_fy2022": last, "last_gift_amount_pre_fy2022": last_amt})
    std_count[d] = 0 if is_trib else count - int(first_type != "Standard")
    typical_gift[d] = 0.6 * last_amt + 0.4 * total / count  # usual gift, based on their own history
    life_count[d], life_amount[d] = count, total
    gave_fys[d], first_fy[d] = {first, last}, first
    fy_amount[d][last] = last_amt * (2 if rng.random() < 0.25 else 1)
    last_gift_amt[d] = last_amt
    apply_donor_codes(d)
    # Past events attended, assumed to be more for repeat donors
    n_events = int(rng.poisson({"Repeat": 1.2, "New": 0.4, "Lapsed": 0.5}[status0]))
    if n_events:
        add_event(d, BASE, n_events)

pre_std_count = dict(std_count)


def status(d, fy):
    if (fy - 1) in gave_fys[d]:
        return "New" if first_fy[d] == fy - 1 else "Repeat"
    if first_fy[d] is not None and first_fy[d] < fy:
        return "Lapsed"
    return "Never"


def tribute_only(d):
    return life_count[d] > 0 and std_count[d] == 0


def is_leadership(d, fy):
    """Gave $500-$1,000 in total in either of the two previous fiscal years.
    (Anyone over $1,000 last year has already moved to the mid-level team.)"""
    return max(fy_amount[d].get(fy - 1, 0), fy_amount[d].get(fy - 2, 0)) >= LEADERSHIP_THRESHOLD


transferred = {}   # donor_id -> fiscal year they moved to the mid-level team


def in_annual_giving(d):
    return d not in transferred


def can_mail(d):
    return donors[d]["has_mailing_address"] and not donors[d]["do_not_mail"]


def can_email(d):
    return donors[d]["has_email"] and not donors[d]["do_not_email"]


def can_call(d):
    return donors[d]["has_phone"] and not donors[d]["do_not_call"]


# GIFTS

gifts = []
PAYMENT = {
    "Direct Mail": (["Check", "Online", "Credit Card"], [0.60, 0.30, 0.10]),
    "Email": (["Online"], [1.0]), "Social Media": (["Online"], [1.0]),
    "Personal Outreach": (["Credit Card", "Online", "Check", "Stock/DAF"], [0.40, 0.25, 0.25, 0.10]),
    "Unsolicited": (["Online", "Check", "Credit Card"], [0.50, 0.35, 0.15]),
}


home_fund = {}   # donor_id -> the fund they chose first (hidden; not in any file)
FUND_CATEGORY_OF = {f: c for c, funds in FUNDS.items() for f in funds}


def choose_fund(d, amt, gift_type):
    if gift_type == "In Memory" and rng.random() < IN_MEMORY_TO_RESTRICTED:
        return pick(FUNDS["Restricted"])
    if d in home_fund and rng.random() < HOME_FUND_LOYALTY:
        return home_fund[d]
    usual = typical_gift[d] if typical_gift[d] is not None else amt
    level = "$500+" if usual >= LEADERSHIP_THRESHOLD else ("$100-$499" if usual >= 100 else "Under $100")
    fund = pick(FUNDS[pick(FUND_CATEGORY_BY_LEVEL[level])])
    home_fund.setdefault(d, fund)
    return fund


# Every gift in a real CRM needs an appeal. Gifts with no clear appeal are credited to a catch-all general annual giving appeal, one per fiscal year.
GENERAL_SEGMENT_GROUP = "Unsolicited"
GENERAL_SEGMENT = "General Annual Giving"


def general_appeal_id(fy):
    return f"FY{str(fy)[2:]}-GEN"


def record_gift(d, gift_date, channel, appeal_id, gift_type="Standard", segment=None, group=None):
    if typical_gift[d] is None:
        key = channel if gift_type == "Standard" else gift_type
        amt = rng.lognormal(np.log(FIRST_GIFT_MEDIAN[key]), FIRST_GIFT_SPREAD)
    else:
        amt = typical_gift[d] * rng.lognormal(0, GIFT_TO_GIFT_SPREAD)
        if channel == "Personal Outreach":
            amt *= PO_ASK_MULTIPLIER
    amt = round_gift(amt)
    fy = fiscal_year(gift_date)
    if appeal_id is None:  # generic appeal
        appeal_id = general_appeal_id(fy)
        group, segment = GENERAL_SEGMENT_GROUP, GENERAL_SEGMENT
    methods, p = PAYMENT[channel]
    if gift_type == "Personal Fundraiser":
        methods, p = ["Online"], [1.0]
    fund = choose_fund(d, amt, gift_type)
    method = rng.choice(methods, p=p)
    received = gift_date
    if method == "Check" and gift_date.month == 1 and gift_date.day <= YEAR_END_CHECK_CUTOFF_DAY:
        gift_date = date(gift_date.year - 1, 12, 31)   # same fiscal year, so nothing else changes
    gifts.append({"donor_id": d, "gift_date": gift_date, "date_received": received, "fiscal_year": fy, "amount": amt,
                  "appeal_id": appeal_id, "segment_group": group, "appeal_segment": segment,
                  "fund": fund, "fund_category": FUND_CATEGORY_OF[fund], "gift_type": gift_type,
                  "payment_method": method})
    life_count[d] += 1
    life_amount[d] += amt
    if typical_gift[d] is None:
        typical_gift[d] = amt
    else:  # usual gift leans toward their most recent gift amount
        typical_gift[d] = RECENT_GIFT_WEIGHT * amt + (1 - RECENT_GIFT_WEIGHT) * typical_gift[d]
    fy_amount[d][fy] = fy_amount[d].get(fy, 0) + amt
    last_gift_amt[d] = amt
    if gift_type == "Standard":
        std_count[d] += 1
    gave_fys[d].add(fy)
    if first_fy[d] is None:
        apply_donor_codes(d)
        first_fy[d] = fy
        donors[d]["first_gift_fy"] = fy
        donors[d]["first_gift_type"] = gift_type


def lagged_date(launch, channel, timing=None):
    # Books close June 30: a response that would land after that is redrawn, so late
    # responses spread across June instead of piling up on the last day of the fiscal year.
    for _ in range(100):
        if channel in ("Email", "Social Media") and timing in ("GT", "FYE"):
            d = launch + timedelta(days=int(rng.exponential(ONLINE_PUSH_LAG_DAYS)))  # same-day giving
            return min(d, fy_end(fiscal_year(launch)))   # last-day pushes: gifts come in by June 30
        else:
            lag = YE_MAIL_LAG_DAYS if (channel == "Direct Mail" and timing == "YE") else LAG_DAYS[channel]
            d = launch + timedelta(days=int(rng.exponential(lag)) + 1)
        if d <= fy_end(fiscal_year(launch)):
            return d
    return fy_end(fiscal_year(launch))



# Appeal Calendar: (timing, channel, segment groups, launch date)

APPEAL_NAME = {
    ("Direct Mail", "ACQ"): "Donor Acquisition Mailing", ("Direct Mail", "FALL"): "Fall Appeal",
    ("Direct Mail", "YE"): "Year-End Appeal", ("Direct Mail", "SPR"): "Spring Appeal",
    ("Direct Mail", "FYE"): "Fiscal Year-End Appeal",
    ("Email", "FALL"): "Fall Email", ("Email", "YE"): "Year-End Email",
    ("Email", "SPR"): "Spring Email", ("Email", "FYE"): "Fiscal Year-End Email",
    ("Email", "GT"): "GivingTuesday Email",
    ("Personal Outreach", "FALL"): "Fall Leadership Outreach",
    ("Personal Outreach", "SPR"): "Spring Leadership Outreach",
    ("Social Media", "GT"): "GivingTuesday Social Posts", ("Social Media", "YE"): "Calendar Year-End Social Posts",
    ("Social Media", "FYE"): "Fiscal Year-End Social Posts",
}
CHANNEL_CODE = {"Direct Mail": "DM", "Email": "EM", "Social Media": "SM", "Personal Outreach": "PO"}
DB_GROUPS = ["Current Donors", "Lapsed Donors", "Never Donors"]
GROUP_STATUSES = {"Current Donors": {"Repeat", "New"}, "Lapsed Donors": {"Lapsed"}, "Never Donors": {"Never"}}


def calendar(fy):
    y0, y1 = fy - 1, fy
    return [
        ("ACQ", "Direct Mail", ["Acquisition (Rented List)"], date(y0, 9, 15)),
        ("FALL", "Personal Outreach", ["Current Donors"], date(y0, 10, 1)),
        ("FALL", "Direct Mail", ["Current Donors"], date(y0, 10, 15)),
        ("FALL", "Email", ["Current Donors", "Lapsed Donors"], date(y0, 10, 20)),
        ("GT", "Email", DB_GROUPS, GIVING_TUESDAY[fy]),
        ("GT", "Social Media", ["General Public"], GIVING_TUESDAY[fy]),
        ("YE", "Direct Mail", DB_GROUPS, date(y0, 12, 1)),
        ("YE", "Email", DB_GROUPS, date(y0, 12, 29)),
        ("YE", "Social Media", ["General Public"], date(y0, 12, 30)),
        ("SPR", "Personal Outreach", ["Current Donors", "Lapsed Donors"], date(y1, 3, 15)),
        ("SPR", "Direct Mail", ["Current Donors"], date(y1, 4, 1)),
        ("SPR", "Email", ["Current Donors", "Lapsed Donors"], date(y1, 4, 8)),
        ("FYE", "Direct Mail", DB_GROUPS, date(y1, 6, 1)),
        ("FYE", "Email", DB_GROUPS, date(y1, 6, 28)),
        ("FYE", "Social Media", ["General Public"], date(y1, 6, 30)),   # last-day push
    ]


# Simulation

segment_rows, solicitations = [], []

for fy in FYS:
    # Donors who gave over $1,000 last year move to the mid-level team
    for d in donors:
        if d not in transferred and fy_amount[d].get(fy - 1, 0) > MID_LEVEL_THRESHOLD:
            transferred[d] = fy

    # Yearly drift in each past donor's usual gift (upgrades and downgrades)
    for d in donors:
        if typical_gift[d] is not None:
            typical_gift[d] = typical_gift[d] * rng.lognormal(*YEARLY_GIFT_DRIFT)

    # New non-donor records added during the year (events, signups, lists)
    for source, (lo, hi) in NEW_NON_DONOR_RECORDS_PER_YEAR.items():
        for _ in range(int(rng.integers(lo, hi))):
            created = date(fy - 1, 8, 1) if source == "Paid List" else random_date(fy_start(fy), fy_end(fy))
            new_record(created, source)

    # Everything about a person used for targeting is frozen at the start of the year
    frozen = {}

    def info(d):
        if d not in frozen:
            last_fy = max(gave_fys[d]) if gave_fys[d] else None
            lvl = gift_level(typical_gift[d]) if typical_gift[d] else None
            frozen[d] = {"status": status(d, fy), "tribute": tribute_only(d), "last_fy": last_fy,
                         "last_amt": last_gift_amt[d], "level": lvl, "leader": is_leadership(d, fy)}
        return frozen[d]

    solicited_once = set()  # one_solicitation_per_year donors already asked this FY

    def once_ok(d):
        return not donors[d]["one_solicitation_per_year"] or d not in solicited_once

    def mail_segment(d):
        """Detailed mailing segment by recency (last gift) and last gift amount."""
        f = info(d)
        if f["status"] in ("Repeat", "New"):
            return "Current - Last Gift " + gift_level(f["last_amt"])
        if f["status"] == "Lapsed":
            years_lapsed = (fy - 1) - f["last_fy"]
            if years_lapsed == 1:
                return "Lapsed 1 Yr - Last Gift " + ("$100+" if f["last_amt"] >= 100 else "Under $100")
            return "Lapsed 2-4 Yrs"
        return "Never Donors"

    for timing, channel, groups, launch in calendar(fy):
        appeal_id = f"FY{str(fy)[2:]}-{CHANNEL_CODE[channel]}-{timing}"
        name = f"FY{fy} {APPEAL_NAME[(channel, timing)]}"
        pool = [d for d in donors if donors[d]["record_created_date"] < launch and in_annual_giving(d)]
        targets = []          # (donor, detailed segment, segment group)
        social = None

        if groups == ["Acquisition (Rented List)"]:
            n_resp = rng.binomial(ACQ_LIST_SIZE, ACQ_RESPONSE)  # rented names
            for _ in range(n_resp):
                gdate = lagged_date(launch, channel)
                d = new_record(gdate, "Acquisition Mailing")
                record_gift(d, gdate, channel, appeal_id, segment="Acquisition (Rented List)",
                            group="Acquisition (Rented List)")
            hard = ACQ_LIST_SIZE * rng.uniform(0.75, 0.90) + rng.uniform(600, 1000)  # includes list rental
            hours = rng.uniform(16, 24)
            segment_rows.append({"appeal_id": appeal_id, "appeal_name": name, "channel": channel,
                                 "fiscal_year": fy, "launch_date": launch,
                                 "segment_group": "Acquisition (Rented List)",
                                 "appeal_segment": "Acquisition (Rented List)", "audience_size": ACQ_LIST_SIZE,
                                 "impressions": None, "link_clicks": None, "hard_cost": hard, "staff_hours": hours})
            continue

        if channel == "Social Media":
            impressions = int(rng.integers(5000, 13500) * (GIVINGTUESDAY_REACH_MULT if timing == "GT" else 1))
            clicks = int(rng.binomial(impressions, SOCIAL_CTR))
            digital_pool = [d for d in pool if donors[d]["has_email"]]
            for _ in range(rng.binomial(clicks, SOCIAL_PAGE_COMPLETION)):
                gdate = lagged_date(launch, channel, timing)
                if rng.random() < SOCIAL_NEW_DONOR_SHARE:
                    # Assumption: new social donors skew younger, like social media users generally
                    d = new_record(gdate, "Social Media", birth_year=int(rng.integers(1960, 2004)))
                else:
                    d = digital_pool[rng.integers(len(digital_pool))]
                record_gift(d, gdate, channel, appeal_id, segment="General Public", group="General Public")
            segment_rows.append({"appeal_id": appeal_id, "appeal_name": name, "channel": channel,
                                 "fiscal_year": fy, "launch_date": launch, "segment_group": "General Public",
                                 "appeal_segment": "General Public", "audience_size": None,
                                 "impressions": impressions, "link_clicks": clicks,
                                 "hard_cost": 0.0, "staff_hours": rng.uniform(3, 6)})  # staff time
            continue

        for group in groups:
            members = [d for d in pool if info(d)["status"] in GROUP_STATUSES[group]]
            if channel == "Direct Mail":
                def mail_ok(d):  # common suppression rules
                    f = info(d)
                    if f["status"] == "Lapsed":
                        return fy - f["last_fy"] <= 5
                    if f["status"] == "Never":
                        return (launch - donors[d]["record_created_date"]).days <= 3 * 365
                    return True
                targets += [(d, mail_segment(d), group) for d in members
                            if can_mail(d) and mail_ok(d) and once_ok(d)]
            elif channel == "Email":
                targets += [(d, group, group) for d in members if can_email(d) and once_ok(d)]
            else:  # Personal Outreach: leadership donors only
                label = "Leadership - " + ("Current" if group == "Current Donors" else "Lapsed")
                for d in members:
                    f = info(d)
                    if not f["leader"] or not (can_call(d) or can_email(d)) or not once_ok(d):
                        continue
                    if group == "Current Donors" and timing == "SPR" and fy in gave_fys[d]:
                        continue  # spring follow-up only for leadership donors who haven't renewed
                    targets.append((d, label, group))

        # Individual solicitations and responses
        solicited_once.update(d for d, _, _ in targets if donors[d]["one_solicitation_per_year"])
        for d, seg, group in targets:
            f = info(d)
            p = RESPONSE[channel][f["status"]]
            if f["level"]:
                p *= GIFT_LEVEL_RESPONSE_MULT[f["level"]]
            if f["tribute"]:
                p *= TRIBUTE_RESPONSE_MULT
            if fy in gave_fys[d]:
                p *= ALREADY_GAVE_THIS_FY_MULT
            if channel in ("Direct Mail", "Email"):
                p *= TIMING_RESPONSE_MULT[channel][timing]
            sol = {"appeal_id": appeal_id, "segment_group": group, "appeal_segment": seg, "donor_id": d,
                   "sent_date": launch, "donor_status_at_fy_start": f["status"],
                   "tribute_only": int(f["tribute"]), "bad_contact_info": 0, "clicked": None,
                   "unsubscribed": None, "contact_method": None, "connected": None}
            if channel == "Direct Mail":
                if rng.random() < BAD_ADDRESS_RATE["Current" if group == "Current Donors" else "Other"]:
                    sol["bad_contact_info"] = 1
                    donors[d]["has_mailing_address"] = 0  # returned mail: address marked bad
                responded = not sol["bad_contact_info"] and rng.random() < p
            elif channel == "Email":
                sol["unsubscribed"] = 0
                if rng.random() < EMAIL_BOUNCE_PER_SEND:
                    sol["bad_contact_info"] = 1
                    donors[d]["has_email"] = 0            # bounced: email removed
                    responded = False
                else:
                    responded = rng.random() < p
                    if not responded and rng.random() < EMAIL_UNSUB_PER_SEND:
                        sol["unsubscribed"] = 1
                        donors[d]["do_not_email"] = 1     # unsubscribed
                sol["clicked"] = int(responded or (not sol["bad_contact_info"] and rng.random() < 0.0059))
            else:  # Personal Outreach
                method = "Phone" if (can_call(d) and (not can_email(d) or rng.random() < 0.6)) else "Personal Email"
                sol["contact_method"] = method
                if method == "Phone" and rng.random() < WRONG_NUMBER_RATE:
                    sol["bad_contact_info"] = 1
                    donors[d]["has_phone"] = 0
                elif method == "Personal Email" and rng.random() < EMAIL_BOUNCE_PER_SEND:
                    sol["bad_contact_info"] = 1
                    donors[d]["has_email"] = 0
                sol["connected"] = int(not sol["bad_contact_info"] and rng.random() < PO_CONNECT_RATE[method])
                responded = sol["connected"] and rng.random() < p
            if responded:
                record_gift(d, lagged_date(launch, channel, timing), channel, appeal_id, segment=seg, group=group)
            solicitations.append(sol)

        # Costs - one row per segment
        seg_sizes = pd.Series([(g, s) for _, s, g in targets]).value_counts() if targets else pd.Series(dtype=int)
        total_n = max(len(targets), 1)
        if channel == "Direct Mail":
            per_piece = rng.uniform(1.00, 1.25)   # Assumption: printing + postage on short, small-shop print runs
            creative, creative_hours = rng.uniform(500, 900), rng.uniform(8, 12)
        elif channel == "Email":
            creative, creative_hours = 0.0, rng.uniform(2, 3)
        for (group, seg), n in seg_sizes.items():
            share = n / total_n
            if channel == "Direct Mail":
                # shared creative split by volume + small per-segment versioning (ask amounts, data pull)
                hard = n * per_piece + creative * share + rng.uniform(50, 100)
                hours = creative_hours * share + 0.5
            elif channel == "Email":
                hard = n * 0.01                       # Assumption: platform cost per send
                hours = creative_hours * share + 0.5
            else:                                     # Assumptions:
                hard = n * rng.uniform(0.5, 1.5)      # notes, small stewardship items
                hours = n * rng.uniform(0.6, 0.9)     # prep, contact, follow-up per prospect
            segment_rows.append({"appeal_id": appeal_id, "appeal_name": name, "channel": channel,
                                 "fiscal_year": fy, "launch_date": launch, "segment_group": group,
                                 "appeal_segment": seg, "audience_size": int(n), "impressions": None,
                                 "link_clicks": None, "hard_cost": hard, "staff_hours": hours})

    # Unsolicited gifts credited to the generic annual giving appeal
    segment_rows.append({"appeal_id": general_appeal_id(fy), "appeal_name": f"FY{fy} General Annual Giving",
                         "channel": "Unsolicited", "fiscal_year": fy, "launch_date": fy_start(fy),
                         "segment_group": GENERAL_SEGMENT_GROUP, "appeal_segment": GENERAL_SEGMENT,
                         "audience_size": None, "impressions": None, "link_clicks": None,
                         "hard_cost": 0.0, "staff_hours": 0.0})
    for d in [d for d in donors if donors[d]["record_created_date"] <= fy_end(fy) and in_annual_giving(d)]:
        f = info(d)
        p = UNSOLICITED_RATE[f["status"]] * (TRIBUTE_RESPONSE_MULT if f["tribute"] else 1)
        if rng.random() < p:
            earliest = max(fy_start(fy), donors[d]["record_created_date"])
            gtype = pick(TRIBUTE_TYPE_MIX) if rng.random() < EXISTING_DONOR_TRIBUTE_SHARE else "Standard"
            when = random_date(earliest, fy_end(fy)) if gtype == "In Memory" else seasonal_date(earliest, fy_end(fy))
            record_gift(d, when, "Unsolicited", None, gtype)
    for _ in range(int(rng.integers(*UNSOLICITED_NEW_DONORS_PER_YEAR))):
        gdate = seasonal_date(fy_start(fy), fy_end(fy))
        record_gift(new_record(gdate, "Unsolicited Gift"), gdate, "Unsolicited", None)
    # New tribute donors (in memory / in honor, and personal fundraisers)
    for _ in range(int(rng.integers(*TRIBUTE_NEW_DONORS_PER_YEAR))):
        gtype = pick(TRIBUTE_TYPE_MIX)
        gdate = random_date(fy_start(fy), fy_end(fy)) if gtype == "In Memory" else seasonal_date(fy_start(fy), fy_end(fy))
        record_gift(new_record(gdate, "Tribute Gift"), gdate, "Unsolicited", None, gtype)
    for _ in range(int(rng.integers(*PERSONAL_FUNDRAISER_NEW_DONORS_PER_YEAR))):
        gdate = random_date(fy_start(fy), fy_end(fy))
        record_gift(new_record(gdate, "Personal Fundraiser"), gdate, "Unsolicited", None, "Personal Fundraiser")

    # Event attendance during the year
    for d in [d for d in donors if donors[d]["record_created_date"] <= fy_end(fy) and in_annual_giving(d)]:
        if donors[d]["acquisition_source"] == "Event Attendee" and fiscal_year(donors[d]["record_created_date"]) == fy:
            continue  # their first event is already counted
        f = info(d)
        p = EVENT_ATTENDANCE_RATE[f["status"]] * (LEADERSHIP_EVENT_MULT if f["leader"] else 1)
        if rng.random() < p:
            add_event(d, fy)


# BUILD TABLES
for d in donors:
    donors[d]["tribute_only"] = int(tribute_only(d))                 # as of end of FY2026
    donors[d]["events_attended"] = int(sum(events_by_fy[d].values()))  # lifetime, as of end of FY2026
    donors[d]["mid_level_transfer_fy"] = transferred.get(d)
col_order = ["donor_id", "birth_year", "age_group", "state", "acquisition_source", "record_created_date",
             "has_mailing_address", "has_email", "has_phone", "do_not_mail", "do_not_call",
             "do_not_email", "one_solicitation_per_year", "prior_gift_count_pre_fy2022",
             "prior_gift_amount_pre_fy2022", "first_gift_fy", "first_gift_type", "tribute_only",
             "last_gift_fy_pre_fy2022", "last_gift_amount_pre_fy2022", "events_attended",
             "mid_level_transfer_fy"]
donors_df = pd.DataFrame(donors.values())[col_order]
for c in ["first_gift_fy", "last_gift_fy_pre_fy2022", "mid_level_transfer_fy"]:
    donors_df[c] = donors_df[c].astype("Int64")

# One row per appeal x segment
seg_df = pd.DataFrame(segment_rows)
seg_df["staff_cost"] = (seg_df["staff_hours"] * STAFF_HOURLY_RATE).round(2)
seg_df["hard_cost"] = seg_df["hard_cost"].round(2)
seg_df["staff_hours"] = seg_df["staff_hours"].round(1)
seg_df["total_cost"] = (seg_df["hard_cost"] + seg_df["staff_cost"]).round(2)

GROUP_ORDER = DB_GROUPS + ["Acquisition (Rented List)", "General Public", GENERAL_SEGMENT_GROUP]
# One row per appeal: totals across its segments
appeals_df = (seg_df.groupby("appeal_id", sort=False)
              .agg(appeal_name=("appeal_name", "first"), channel=("channel", "first"),
                   fiscal_year=("fiscal_year", "first"), launch_date=("launch_date", "first"),
                   segment_groups_targeted=("segment_group", lambda x: "; ".join(sorted(dict.fromkeys(x), key=GROUP_ORDER.index))),
                   number_of_segments=("appeal_segment", "nunique"),
                   audience_size=("audience_size", lambda x: x.sum(min_count=1)),
                   impressions=("impressions", lambda x: x.sum(min_count=1)),
                   link_clicks=("link_clicks", lambda x: x.sum(min_count=1)),
                   hard_cost=("hard_cost", "sum"), staff_hours=("staff_hours", "sum"),
                   staff_cost=("staff_cost", "sum"), total_cost=("total_cost", "sum"))
              .reset_index())
for c in ["hard_cost", "staff_hours", "staff_cost", "total_cost"]:
    appeals_df[c] = appeals_df[c].round(2)
for c in ["audience_size", "impressions", "link_clicks"]:
    appeals_df[c] = appeals_df[c].astype("Int64")
segments_df = seg_df[["appeal_id", "segment_group", "appeal_segment", "audience_size",
                      "hard_cost", "staff_hours", "staff_cost", "total_cost"]].copy()
segments_df["audience_size"] = segments_df["audience_size"].astype("Int64")

sol_df = pd.DataFrame(solicitations)
sol_df.insert(0, "solicitation_id", [f"S{i:06d}" for i in range(1, len(sol_df) + 1)])
for c in ["clicked", "unsubscribed", "connected"]:
    sol_df[c] = sol_df[c].astype("Int64")

gifts_df = pd.DataFrame(gifts).sort_values(["gift_date", "donor_id"]).reset_index(drop=True)
gifts_df.insert(0, "gift_id", [f"G{i:06d}" for i in range(1, len(gifts_df) + 1)])

# Donor x fiscal year summary (everyone on file, including non-donors)
rows = []
fy_totals = gifts_df.groupby(["donor_id", "fiscal_year"])["amount"].agg(["count", "sum"])
fy_std = gifts_df[gifts_df.gift_type == "Standard"].groupby(["donor_id", "fiscal_year"]).size()
for dn in donors_df.itertuples(index=False):
    d = dn.donor_id
    cum_n, cum_amt = dn.prior_gift_count_pre_fy2022, dn.prior_gift_amount_pre_fy2022
    cum_std = pre_std_count[d] if d in pre_std_count else 0
    cum_events = sum(v for k, v in events_by_fy[d].items() if k < START_FY)
    prior_fys = {dn.first_gift_fy, dn.last_gift_fy_pre_fy2022} if cum_n else set()
    ever = bool(prior_fys)
    for fy in FYS:
        if dn.record_created_date > fy_end(fy):
            continue
        if pd.notna(dn.mid_level_transfer_fy) and fy >= dn.mid_level_transfer_fy:
            # No longer part of annual giving: giving fields left blank, totals frozen at transfer
            rows.append({"donor_id": d, "fiscal_year": fy, "gave_this_fy": None, "fy_gift_count": None,
                         "fy_gift_amount": None, "giving_level_fy": None,
                         "donor_status_fy": "Transferred to Mid-Level",
                         "tribute_only_as_of_fy_end": int(cum_n > 0 and cum_std == 0),
                         "events_attended_as_of_fy_end": int(cum_events),
                         "lifetime_gift_count_as_of_fy_end": int(cum_n),
                         "lifetime_gift_amount_as_of_fy_end": round(float(cum_amt), 2)})
            continue
        n, amt = fy_totals.loc[(d, fy)] if (d, fy) in fy_totals.index else (0, 0.0)
        if n > 0:
            s = "Retained" if (fy - 1) in prior_fys else ("Reactivated" if ever else "New")
        else:
            s = "Lapsed" if ever else "Non-donor"
        cum_n += n
        cum_amt += amt
        cum_std += int(fy_std.get((d, fy), 0))
        cum_events += events_by_fy[d].get(fy, 0)
        rows.append({"donor_id": d, "fiscal_year": fy, "gave_this_fy": int(n > 0),
                     "fy_gift_count": int(n), "fy_gift_amount": round(float(amt), 2),
                     "giving_level_fy": gift_level(amt) if n > 0 else None,
                     "donor_status_fy": s,
                     "tribute_only_as_of_fy_end": int(cum_n > 0 and cum_std == 0),
                     "events_attended_as_of_fy_end": int(cum_events),
                     "lifetime_gift_count_as_of_fy_end": int(cum_n),
                     "lifetime_gift_amount_as_of_fy_end": round(float(cum_amt), 2)})
        if n > 0:
            prior_fys.add(fy)
            ever = True
summary_df = pd.DataFrame(rows)
for c in ["gave_this_fy", "fy_gift_count"]:
    summary_df[c] = summary_df[c].astype("Int64")


# Benchmark Check: comparing the simulated results to the benchmarks

g = gifts_df.merge(appeals_df[["appeal_id", "channel"]], on="appeal_id", how="left")
seg_ch = segments_df.merge(appeals_df[["appeal_id", "channel"]], on="appeal_id")
checks = []


def add(metric, simulated, benchmark, source):
    checks.append({"metric": metric, "simulated": simulated, "benchmark": benchmark, "source": source})


def rate(channel, groups):
    a = seg_ch[(seg_ch.channel == channel) & seg_ch.segment_group.isin(groups)]
    gg = g[(g.channel == channel) & g.segment_group.isin(groups)]
    return a, gg


FEP = "Fundraising Effectiveness Project, Q4 2025 Report"
ANA = "ANA 2024 Response Rate Report (house lists, all industries; via Printing Impressions summary)"
GREENFIELD = "Greenfield, Fund-Raising: Evaluating and Managing the Fund Development Process (1999); Greenfield, Reasonable Cost Guidelines"
MR = "M+R Benchmarks 2026, Email Messaging"
BLOOMERANG = "Bloomerang, Memorial and Tribute Donors Can Be Retained (With Some Help)"

a, gg = rate("Direct Mail", ["Current Donors", "Lapsed Donors"])
add("Direct mail response, existing donors (current + lapsed)", f"{len(gg) / a.audience_size.sum():.1%}",
    "5% to 9%", ANA)
add("Cost to raise $1, direct mail to existing donors", f"${a.total_cost.sum() / gg.amount.sum():.2f}",
    "$0.20 to $0.25", GREENFIELD)
a, gg = rate("Direct Mail", ["Acquisition (Rented List)"])
add("Cost to raise $1, direct mail acquisition", f"${a.total_cost.sum() / gg.amount.sum():.2f}",
    "$1.00 to $1.50", GREENFIELD)
a, gg = rate("Email", DB_GROUPS)
add("Email response rate (all segments)", f"{len(gg) / a.audience_size.sum():.2%}", "0.05%", MR)
add("Email revenue per 1,000 sent", f"${gg.amount.sum() / a.audience_size.sum() * 1000:.0f}", "$54", MR)
em = sol_df[sol_df.appeal_id.str.contains("-EM-")]
per_year_bounce = (em.groupby(em.appeal_id.str[:4]).bad_contact_info.sum()
                   / em.groupby(em.appeal_id.str[:4]).donor_id.nunique())
add("Email addresses lost to bounces per year", f"{per_year_bounce.mean():.1%}", "4%", MR)

ret = []
for fy in FYS[1:]:
    moved = set(summary_df[(summary_df.fiscal_year == fy) &
                           (summary_df.donor_status_fy == "Transferred to Mid-Level")].donor_id)
    prev = summary_df[(summary_df.fiscal_year == fy - 1) & (summary_df.gave_this_fy == 1)
                      & ~summary_df.donor_id.isin(moved)]   # moved to mid-level: not a loss
    cur = set(summary_df[(summary_df.fiscal_year == fy) & (summary_df.gave_this_fy == 1)].donor_id)
    ret.append(prev.assign(retained=prev.donor_id.isin(cur)))
ret = pd.concat(ret)
new = ret[ret.donor_status_fy == "New"]
add("Donor retention, overall", f"{ret.retained.mean():.1%}", "43.3%", FEP)
add("Donor retention, new donors", f"{new.retained.mean():.1%}", "18.9%", FEP)
add("Donor retention, repeat donors", f"{ret[ret.donor_status_fy != 'New'].retained.mean():.1%}", "59.3%", FEP)
add("Retention, new tribute donors", f"{new[new.tribute_only_as_of_fy_end == 1].retained.mean():.1%}",
    "single digits", BLOOMERANG)
bench_df = pd.DataFrame(checks)

# save the output files
os.makedirs("data", exist_ok=True)
donors_df.to_csv("data/donors.csv", index=False)
appeals_df.to_csv("data/appeals.csv", index=False)
segments_df.to_csv("data/appeal_segments.csv", index=False)
sol_df.to_csv("data/solicitations.csv", index=False)
gifts_df.to_csv("data/gifts.csv", index=False)
summary_df.to_csv("data/donor_fy_summary.csv", index=False)
bench_df.to_csv("data/benchmark_check.csv", index=False)

print(f"people: {len(donors_df):,} | appeals: {len(appeals_df)} | solicitations: {len(sol_df):,} | "
      f"gifts: {len(gifts_df):,} | donor-year rows: {len(summary_df):,}\n")
print(bench_df.to_string(index=False))
