# Who Will Give Next Year? A Cost-Based Model for Mail vs. Email

A machine learning model that estimates each past donor's chance of giving next year, then decides who should get direct mail and who should be reached by email only.

This is the third part of an annual giving project built on a synthetic (simulated) donor database:

| Part | What it covers | README |
|---|---|---|
| 1. Data | How the synthetic dataset was built, data dictionary, assumptions | [README_generatedata.md](README_generatedata.md) |
| 2. SQL analysis | Channel ROI, segment performance, new donor retention | [README_workbook.md](README_workbook.md) |
| 3. Give-again model | Predicting individual donors and choosing a channel for each | This file |

The SQL analysis showed which *groups* of donors are likely to give again. This model goes one step further and scores *each donor*, so mail goes to the people most likely to respond and everyone else is reached through lower-cost email.

**[View the full model notebook →](../next_gift_model.ipynb)**

See the [main README](../README.md) for the full project.

---

## In short

- **The question:** which past donors will give next year, and which of them are worth the cost of a mailing?
- **The answer:** the model mails 44% of the donor file, reaches 88% of the people who go on to give, and produces slightly more net revenue than the mailing rules it was compared against, while spending less on postage than mailing everyone.
- **The biggest lever isn't the model:** 2,016 donors in next year's file can't be reached by mail or email, and 374 are worth mailing but have no usable address. Keeping contact information up to date matters as much as who gets picked.

> All data is simulated. No real donor information is used.

---

## The business problem

An annual giving program sends several fundraising appeals a year. Mail costs about $0.70 per piece; email costs almost nothing. The question is who should get the more expensive mail.

The two possible mistakes are not equally costly:

| Mistake | What it costs |
|---|---|
| Mail someone who doesn't give | About $0.70 per mailing |
| Skip someone who would have given | Their whole gift (typically $50–$100), and possibly the relationship |

Because missing a donor costs far more than an extra stamp, the model doesn't simply ask "will this person give, yes or no?" It asks whether mailing them is **worth the money**:

> **Mail a donor if: chance of giving × expected gift > cost of mailing them for a year**

**Example:** a donor with a 5% chance of giving $60 is worth $3 on average (0.05 × $60). If mailing them all year costs $2.59, they get mail.

Donors who don't clear that bar are **not dropped**. They stay on the email list. The model only decides which channel each person gets; it never removes anyone from the program.

---

## How it works, step by step

### 1. Use only what was known at the time

The model learns from past years: "here is what we knew about a donor at the end of one year, and here is whether they gave the next year." For that to be a fair test, each year's information has to look exactly as it did at that point, with nothing from the future mixed in. (Data scientists call this avoiding **leakage**.)

The donor file is a snapshot from the end of FY2026, so it shows today's contact information, not what the organization had in earlier years. The notebook rebuilds each donor's record year by year:

- **Addresses, emails, and phone numbers** are restored for the years before a piece of mail was returned, an email bounced, or a number turned out to be wrong.
- **Do Not Email** is turned on starting the year the donor unsubscribed.
- **Do Not Mail, Do Not Call, and One Solicitation Per Year** codes don't come with a date. The notebook works out when each started from what the donor was actually sent: someone who received mail in FY2024 couldn't have had Do Not Mail yet. Only 18 donors turned out to have picked up a code partway through, but the check would matter more in a real CRM.

### 2. Describe each donor in numbers

Each donor gets one row per year, describing what was known about them at the end of that year:

| Group | What it describes |
|---|---|
| Recency | Years since their last gift |
| Gift history | Last gift amount, average gift, lifetime number of gifts, whether they only give tribute gifts |
| How they give | Gifts by mail, personal outreach, and unsolicited gifts; email clicks; events attended |
| Reachability | Whether they can be mailed, emailed, or called, and any solicitation codes |
| Background | Age group, how they were first acquired |

### 3. Remove fields that repeat each other

A CRM export often contains several fields that say the same thing in different ways. Duplicates don't help accuracy, and they make it harder to see what's driving the results, so two cleanup steps were tested and kept:

- **One measure of recency.** Four fields described timing (gave this year, gave last year, years since last gift, years since first gift). *Years since last gift* alone performed just as well, so it's the only one kept.
- **No repeated fields.** This year's gift count, gift amount, and giving level all just mean "gave this year." Address and email fields were already combined into "can be mailed" and "can be emailed." Lifetime gift amount can be calculated from average gift and lifetime gift count. These were removed.

The model went from 29 inputs to 18, and the chosen model's accuracy slightly improved.

### 4. Train on the past, test on a year the model hasn't seen

| Step | Years | Purpose |
|---|---|---|
| Train | FY2022→23, FY2023→24, FY2024→25 | The model learns patterns from these years |
| Pick the best model | FY2024 | Compare four methods on a year held back from training |
| Final test | FY2025→26 | A year the model never saw, to show how it would perform for real |
| Plan next year | FY2026 donors | Refit the chosen model on all four labeled years (FY2022→23 through FY2025→26), then score current donors to build the FY2027 mail and email plan |

### 5. Compare four methods

| Method | How it works, in plain terms |
|---|---|
| **Logistic regression** | Gives each fact about a donor a weight and adds them up into a score. Simple and easy to explain. |
| **Decision tree** | A flowchart of yes/no questions ("Gave in the last year?" → "Can be mailed?"). The easiest to show a non-technical team. |
| **Random forest** | Builds hundreds of flowcharts on different slices of the data and averages them. |
| **Gradient boosting** | Builds hundreds of small flowcharts one after another, each fixing the mistakes of the ones before. Usually the most accurate, but the hardest to explain. |

### 6. Check that the percentages can be trusted

The mailing decision multiplies each donor's chance of giving by a dollar amount, so the percentages have to be accurate, not just the ranking. If the model says 20% when the truth is 10%, it doubles that donor's apparent value and mails people who aren't worth the postage.

The **Brier score** measures this. It's explained in full under [How the results are measured](#how-the-results-are-measured). The short version: the chosen model's percentages are about 40% more accurate than giving every donor the same average chance. A chart comparing predicted chances with actual giving also lines up closely, so the percentages are reliable enough to multiply by dollars.

### 7. Turn the scores into a mailing decision

- **Expected gift:** the donor's last gift × 1.16. In past years, donors who gave again typically gave about 16% more in total than their last gift, partly because some gave twice.
- **Cost of mailing for a year:** $0.70 per piece × the number of mailings. Current donors get about 3.7 mailings a year (**$2.59**); lapsed donors get about 1.9 (**$1.30**). Only the cost of adding one more name counts, since design and staff time are spent either way.
- **Only reachable donors get mail.** A donor needs a usable mailing address and no Do Not Mail code.

---

## How the results are measured

| Measure | What it tells you |
|---|---|
| **Recall** | Of everyone who gave next year, the share who were on the mail list. Higher means fewer givers missed. |
| **Precision** | Of everyone mailed, the share who gave. Higher means less postage spent on non-givers. |
| **Net value** | Next year's gifts from mailed donors, minus the cost of mailing them. It assumes every gift came from the mailing, so it's generous, but it's applied the same way to every approach. |
| **PR-AUC** | Whether the model puts future givers near the top of its list, from 0 to 1. Higher is better. Used to pick the best model. Explained below. |
| **ROC-AUC** | A second ranking measure, shown for reference. Explained below. |
| **Brier score** | Whether the model's percentages match what actually happened. Lower is better, and 0 is perfect. Explained below. |

### PR-AUC: does the model put the givers at the top?

Imagine sorting every donor from most to least likely to give, then mailing from the top of the list down. Along the way, you track two things:

- **Precision:** of the people mailed so far, what share gave?
- **Recall:** of everyone who eventually gave, what share has been reached so far?

A good list puts givers near the top, so most of them are reached early while precision is still high. A poor list scatters them throughout, so almost everyone has to be mailed to find them. PR-AUC (area under the precision-recall curve) sums this up across the whole list in one number.

**What counts as good:** a list in random order scores about the share of donors who give, roughly **0.115** in the year used to pick the model. The chosen model scores **0.605, about five times better than chance**.

**Why PR-AUC instead of the more common ROC-AUC:** only about 1 in 9 donors gives the next year. ROC-AUC gives models credit for spotting the many obvious non-givers, so it makes every model look good: all four scored 0.89–0.90, even though they differed a lot at finding the actual givers. PR-AUC focuses on the rare givers, which is what the mailing decision depends on.

### Brier score: are the percentages honest?

The model doesn't just rank donors; it gives each one a percentage, like "15% chance of giving." For each donor, the Brier score takes the predicted chance, subtracts what actually happened (1 if they gave, 0 if not), and squares the difference. The score is the average across all donors.

| Predicted chance | Did they give? | Score for that donor |
|---|---|---|
| 80% | Yes | (0.80 − 1)² = 0.04, close |
| 80% | No | (0.80 − 0)² = 0.64, badly wrong |
| 5% | No | (0.05 − 0)² = 0.0025, close |
| 5% | Yes | (0.05 − 1)² = 0.90, badly wrong |

Being confident and right costs almost nothing; being confident and wrong costs a lot.

**What counts as good:** giving every donor the same chance (10.3%, the share who gave in the test year) scores **0.092**. The chosen model scores **0.055, about 40% better**.

### Why the model needs both

The mailing rule multiplies each donor's percentage by their expected gift, so two things have to be right:

- **The ranking (PR-AUC):** the right people end up near the top.
- **The percentages (Brier score):** the numbers being multiplied by dollars are accurate.

A model could rank donors perfectly but say 30% for donors whose true chance is 10%. Its PR-AUC would look great, but every donor would look three times more valuable than they are, and far too many people would be mailed. That's why the best model is picked on PR-AUC, and its Brier score is checked before the dollar calculations are trusted.

---

## Results

### Picking the model (FY2024, held back from training)

| Model | PR-AUC | ROC-AUC | Brier |
|---|---|---|---|
| **Gradient boosting (chosen)** | **0.605** | 0.898 | 0.064 |
| Logistic regression | 0.567 | 0.894 | 0.066 |
| Random forest | 0.566 | 0.887 | 0.066 |
| Decision tree | 0.517 | 0.890 | 0.068 |

Gradient boosting ranked donors best. Logistic regression was close before the duplicate fields were removed, but lost some accuracy without them. It treats every extra year since a donor's last gift as equally important, while the real drop-off is sharpest right after someone stops giving. The tree-based methods pick up on that on their own.

### Final test (FY2025 donors → did they give in FY2026?)

The model is compared with mailing rules an office might use without a model. Every approach only mails donors who can actually be mailed.

| Approach | Donors mailed | % of file | Recall | Precision | Net value |
|---|---|---|---|---|---|
| **Gradient boosting (chosen)** | **2,104** | **44.0%** | **88.0%** | **20.6%** | **$86,212** |
| Logistic regression | 1,980 | 41.4% | 86.8% | 21.6% | $86,353 |
| Random forest | 2,188 | 45.7% | 88.8% | 20.0% | $86,431 |
| Decision tree | 2,081 | 43.5% | 88.6% | 21.0% | $86,182 |
| Rule: gave in the last 5 years | 1,933 | 40.4% | 89.4% | 22.8% | $85,895 |
| Rule: gave in the last 2 years | 1,129 | 23.6% | 79.7% | 34.7% | $79,816 |
| Mail every mailable donor | 2,744 | 57.4% | 91.7% | 16.4% | $86,172 |

The four models land within about $250 of each other on the test year, which is normal year-to-year variation. The model was chosen on FY2024, before these results were seen, so it isn't switched based on them.

### Key findings

- **The model mails different people, not just fewer.** Compared with "gave in the last 5 years," it adds 361 long-lapsed donors whose past gifts make them worth mailing and drops 190 donors whose expected gift doesn't cover the postage. Net value comes out $317 higher.
- **It saves postage without losing revenue.** Compared with mailing every mailable donor, it mails 23% fewer people (2,744 → 2,104) and spends about $880 less, while keeping 99% of the gift revenue from mailed donors.
- **Net value barely moves between approaches, and that's expected.** A mailing costs about $0.70, and a gift is usually worth $50 or more, so mailing an extra donor rarely loses money. The approach that clearly loses is cutting too deep: "gave in the last 2 years" misses 20% of givers and gives up about $6,400.
- **Reachability is a major factor.** Being mailable is the second strongest predictor. Of the 59 givers the model didn't mail, 32 had no usable mail or email at all.
- **The decision holds up if costs rise.** If mailing cost twice as much, the mail list would shrink by 22% (2,104 → 1,637), but net value would drop by only $60.

### What predicts giving again

The model's top predictors were found by shuffling one field at a time and measuring how much worse the model got. A big drop means the model relies on that field.

| Rank | Predictor | Givers vs. non-givers |
|---|---|---|
| 1 | Years since last gift | Givers gave more recently (0.75 vs. 4.4 years on average) |
| 2 | Can be mailed | 92% of givers vs. 53% of non-givers |
| 3 | Lifetime number of gifts | Givers have given more often |
| 4 | Has only ever made tribute gifts | Much less common among givers |
| 5 | One Solicitation Per Year code | Much less common among givers |
| 6 | Size of last gift | Slightly larger among givers |

Most other fields, such as age group, events attended, and email clicks, have almost no influence. That's expected: in the simulation, giving is driven by recency, gift history, reachability, tribute status, and solicitation codes, and none of the rules use age, events, or email clicks. The model picking out exactly the rules that were built in, and ignoring the rest, is a good sign that it works correctly. In a real CRM, those other fields might well matter, so they're kept in.

### Next year's channel plan (FY2026 donors scored for FY2027)

| Recommendation | Who | Donors |
|---|---|---|
| Mail + email | Worth mailing and can be mailed | 2,088 |
| Email only: find mailing address | Worth mailing, but no usable address | 374 |
| Email only | Not worth mailing, but has a usable email | 748 |
| No mail or email: update contact info | No usable way to reach them | 2,016 |
| **Total** | | **5,226** |

The output file, [`fy2027_solicitation_scores.csv`](../outputs/fy2027_solicitation_scores.csv), lists every donor with their chance of giving, expected gift, expected value, cost to mail, and recommendation. It's sorted by expected value, so the team can trim from the bottom if the budget is tight.

### Recommendations

1. **Use the model's mail list instead of a fixed recency rule.** It reaches nearly as many givers while mailing the right lapsed donors and skipping low-value ones.
2. **Start with the 374 "find mailing address" donors.** They're worth mailing, and a contact-information update is all that stands in the way.
3. **Treat contact-information upkeep as fundraising work.** Unreachable donors make up a large share of the file, and reachability is one of the strongest predictors of giving.
4. **Revisit the cost assumptions each year.** The mail list shrinks noticeably as costs rise, even though net value barely changes.

---

## The same model in business terms

| Fundraising term | Business equivalent |
|---|---|
| Will this donor give next year? | Will this customer buy again? (repeat-purchase or churn model) |
| Mail only when expected gift beats mail cost | Expected-value targeting: contact a customer only when expected revenue beats the cost of contact |
| Mail vs. email | Expensive vs. low-cost marketing channel |
| Expected gift | Expected order value |
| Years since last gift | Recency, as in RFM segmentation |
| Gains chart | Lift / cumulative gains for campaign targeting |

---

## How to run it

See [How to run it](../README.md#how-to-run-it) in the main README.

## Limitations

- **Simulated data.** The model can only learn the rules built into `generate_data.py`. The results show that the method works, not how real donors behave. Every assumption is listed in [README_generatedata.md](README_generatedata.md).
- **Net value is an upper bound.** Some mailed donors would have given anyway.
- **Simple gift estimate.** The expected gift is the last gift times a single factor. A separate model of gift size could improve it.
- **Only mail costs are counted.** Email is close to free, and personal outreach is a separate staffing decision.

## Repository contents

See [Repository contents](../README.md#repository-contents) in the main README.

## Tools

Python, pandas, NumPy, scikit-learn, Matplotlib, Jupyter

## Author

Laura Solarz, MS in Business Analytics candidate, Brandeis University
