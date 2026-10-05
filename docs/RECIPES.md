# Recipes

Prompts that work, grouped by what you're trying to get done. Adapt the wording —
these are shapes, not incantations.

A note that applies to all of them: **for anything that writes, ask for the plan
first.** *"Show me what you'd post, then wait for me."* It costs one turn and
catches the wrong-id mistake before 30 students see it.

- [Start of term](#start-of-term)
- [Weekly course building](#weekly-course-building)
- [Monitoring and triage](#monitoring-and-triage)
- [Grading](#grading)
- [Feedback and communication](#feedback-and-communication)
- [Reading student work](#reading-student-work)
- [End of term](#end-of-term)
- [Cleanup (destructive tier)](#cleanup-destructive-tier)
- [Escape hatches](#escape-hatches)
- [Prompting notes](#prompting-notes)

---

## Start of term

**Orient the assistant**

> What's my Canvas auth status, and which courses am I teaching this term?

**Audit a copied course.** Course copies drag last term's dates with them, and this
is the single highest-value thing on this page:

> List every assignment with its due date, unlock date, and published state. Flag
> anything whose dates fall outside this term — the term runs Aug 25 to Dec 12,
> 2026.

**Check the gradebook adds up**

> List the assignment groups with their weights. Do they sum to 100? Then list
> every assignment and which group it's in — is anything uncategorised?

**Shift all the dates**

> Every assignment is dated from last fall. Move each due date forward by 371 days
> (53 weeks, so weekdays line up). Show me the full old → new table before you
> change anything.

**Set up the structure**

> Create assignment groups: Participation (10%), Reading Responses (20%),
> Essays (45%), Final Project (25%).

**Write the syllabus in**

> Here's my syllabus as markdown. Convert it to clean HTML and set it as the course
> syllabus. Keep the existing "Academic Integrity" section at the bottom unchanged
> — read the current syllabus first.

---

## Weekly course building

**A whole week at once**

> Create an unpublished module "Week 9 — Bonhoeffer and the Limits of Obedience".
> In it:
> 1. A SubHeader "Read"
> 2. A page "Week 9 Reading Guide" with the questions below
> 3. A discussion "Week 9: Costly Grace" due Friday Oct 30 at 11:59pm,
>    requiring an initial post before students can see replies
> 4. The existing assignment "Essay 3" (find its id)
>
> Leave everything unpublished.

**Clone last week's shape**

> Show me the items in the Week 8 module. Build a Week 9 module with the same
> structure but with these new titles and readings — unpublished.

**Release it**

> Show me everything in the Week 9 module and its publish state. If it all looks
> complete, publish the module.

**Check for gaps**

> List all modules with their items. Which weeks are missing a reading page, and
> which have no graded assessment?

**Upload and link**

> Upload `~/course/week9/bonhoeffer-excerpt.pdf` to a "Readings" folder in Files,
> then add it to the Week 9 module as "Bonhoeffer, Ethics (excerpt)".

---

## Monitoring and triage

**Before office hours**

> Who hasn't submitted Essay 2? For each of them, tell me whether they submitted
> the previous two assignments, so I know who's having a bad week versus who's
> disengaged.

**The grading queue**

> List assignments in the "ungraded" bucket with how many submissions each is
> waiting on. Sort by due date — oldest first.

**Students in trouble**

> Pull the gradebook. Which students are below 70% overall, and for each, which
> specific assignments are dragging them down?

**Participation**

> List the discussion topics for weeks 5 through 9. For each, who posted and who
> didn't? Give me the students who have missed three or more.

**Late patterns**

> For every assignment this term, list submissions marked late. Which students show
> up more than twice?

**What's coming**

> What's due in the next ten days — assignments and calendar events together?

---

## Grading

**Completion grading**

> List submissions for "Reading Response 4". For everyone who submitted on time
> with any content, give 5/5 and the comment "Received — thanks."
> Show me the list before you post.

**Grade from a list you already have**

> Here are the scores from my grading spreadsheet, by student name:
> Dana 18, Yusuf 20, Chen 15, Mariam 19.
> Match each to a Canvas user id from the roster, show me the mapping, and then
> bulk-grade "Essay 2".

The name → id mapping step is where errors hide. Always have it shown.

**Excuse rather than zero**

> Mark Dana excused for "Quiz 3" — they had an approved absence.

**Nudge the missing**

> List students with no submission for Essay 2. Draft a short, kind message asking
> them to check in with me this week, and show it to me before sending.

**Sanity-check your own grading**

> For "Essay 1", show me the score distribution and the five lowest-scoring
> submissions with the comments I left. Was I consistent?

---

## Feedback and communication

**Announce something**

> Draft an announcement: Thursday's class is moving to the library seminar room,
> and the Essay 2 deadline is extended to Sunday 11:59pm. Friendly, three sentences.
> Show me the text before posting.

**Schedule it**

> Post that as an announcement but schedule it for Monday at 8am.

**Message a specific group**

> Message the four students who haven't submitted Essay 2 individually — not as a
> group thread — asking them to email me by Friday.

`canvas_message_students` defaults to individual messages precisely so that a note
about missing work doesn't disclose to each recipient who else is behind.

**Per-student feedback**

> Read my submission comments on Essay 1. For each student, write one sentence of
> forward-looking advice for Essay 2, and post it as a comment on their Essay 2
> submission. Show me all of them first.

---

## Reading student work

Consider a read-only posture for this (`CANVAS_ENABLE_WRITES=0`). Student-authored
text is untrusted input — see [SAFETY.md](SAFETY.md#prompt-injection).

**Summarise a discussion**

> Summarise the Week 4 discussion. What are the three most common
> misunderstandings, and which students should I follow up with?

**Find the themes**

> Read all submissions for "Reading Response 3". What questions are students
> actually asking? Group them into themes.

**Prepare class from the submissions**

> Based on the Week 6 responses, draft three discussion questions for Thursday that
> target where students are confused.

**Download for offline marking**

> Download all file attachments for "Final Project Draft" to `~/grading/drafts`.

---

## End of term

**Find the holes**

> List every assignment with ungraded submissions. For each, how many and whose?

**Final-grade sanity check**

> Pull the complete gradebook. Which students are within two points of a letter
> boundary? Which have a missing assignment that would change their grade if I
> accepted it late?

**Close out content**

> List unpublished assignments and pages. Should any of these have gone live?

**Archive**

> Export the gradebook as a table I can paste into a spreadsheet. Use student names
> and every assignment, with points possible in the header row.

---

## Cleanup (destructive tier)

Requires `CANVAS_ALLOW_DESTRUCTIVE=1`. Turn it on for the task, then turn it off.

**Remove a duplicated import**

> The course copy created duplicate modules — "Week 1" appears twice. Show me both
> with their items, and then delete the empty one.

**Drop a never-used assignment**

> "Practice Quiz (old)" has no submissions and isn't in any module. Confirm that,
> then delete it.

**Conclude a withdrawn student**

> Chen Wei withdrew from the course. Conclude their enrollment — do not delete it;
> I need their grades retained.

`conclude` is the default for exactly this reason. `delete` destroys submissions.

---

## Escape hatches

For Canvas features with no dedicated tool.

**Read anything**

> Use the raw API to GET `courses/12345/rubrics` and show me the rubric names.
>
> GET `courses/12345/gradebook_history/feed` — what grade changes happened this
> week?
>
> GET `courses/12345/analytics/student_summaries` — who has the lowest page-view
> count?

**Write anything** (destructive tier)

> POST to `courses/12345/assignment_groups/4421/assignments` with
> `{"assignment[name]": "Make-up Essay", "assignment[points_possible]": 20}`.

`canvas_api_write` has no guardrails at all — it's as powerful as your token. The
[Canvas LMS REST API docs](https://canvas.instructure.com/doc/api/) are the
reference.

---

## Prompting notes

**Name the course when you have several.** With `CANVAS_DEFAULT_COURSE_ID` set, an
unqualified request goes to the default. If you teach two sections, say which.

**Ask for a plan before a mutation.** *"Show me, then wait."*

**Ask for ids alongside names.** *"List students with their Canvas user ids"* makes
the follow-up grading request unambiguous.

**Narrow before raising limits.** If output is truncated, ask for one section or
one assignment rather than raising `CANVAS_MAX_CHARS`. The caps exist to protect
your context window, and a narrower question usually gives a better answer anyway.

**Let it chain.** *"Find the ungraded assignment with the oldest due date, list its
submissions, and tell me who's missing"* is one request. The tools compose.

**Correct it in place.** *"No, that's last term's section — use 12345"* works
better than restarting.
