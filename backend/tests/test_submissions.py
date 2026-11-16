"""Tests of the submission tracker (SPEC-v2 3.18, clipforge.submissions): a
submission for each published post of a campaign project, the copy text with
the post URL and the campaign's required information, and the status
machine with the dates and numbers the owner enters."""

import pytest
from clipforge import campaigns, submissions
from clipforge.models import SubmissionPatch
from clipforge.submissions import IllegalSubmissionMove, SubmissionNotFound
from sqlalchemy import Engine
from submission_fakes import URL, account, campaign_clip, new_campaign, publish


def only(engine: Engine) -> submissions.SubmissionView:
    (view,) = submissions.list_submissions(engine)
    return view


def move(
    engine: Engine, submission_id: int, **fields: object
) -> submissions.SubmissionView:
    return submissions.update_submission(
        engine, submission_id, SubmissionPatch.model_validate(fields)
    )


def test_a_published_campaign_post_gets_a_not_submitted_submission(
    engine: Engine,
) -> None:
    campaign = new_campaign(engine)
    clip_id = campaign_clip(engine, campaign.id, "Best slice")
    post_id = publish(engine, clip_id, account(engine))

    view = only(engine)

    assert (view.post_id, view.campaign_id, view.status) == (
        post_id,
        campaign.id,
        "not_submitted",
    )
    assert (view.submitted_at, view.approved_views, view.payout_usd) == (
        None,
        None,
        None,
    )
    assert (view.platform, view.post_url, view.clip_id, view.clip_title) == (
        "youtube",
        URL,
        clip_id,
        "Best slice",
    )
    assert view.campaign_name == "Pizza Clips"


def test_listing_twice_makes_each_submission_once(engine: Engine) -> None:
    campaign = new_campaign(engine)
    publish(engine, campaign_clip(engine, campaign.id), account(engine))

    first = submissions.list_submissions(engine)
    move(engine, first[0].id, status="submitted")
    again = submissions.list_submissions(engine)

    assert [s.id for s in again] == [s.id for s in first]
    assert again[0].status == "submitted"


def test_only_published_posts_of_campaign_projects_with_a_url_count(
    engine: Engine,
) -> None:
    campaign = new_campaign(engine)
    youtube = account(engine)
    publish(engine, campaign_clip(engine, None), youtube)
    publish(engine, campaign_clip(engine, campaign.id), youtube, url=None)

    assert submissions.list_submissions(engine) == []


def test_the_list_is_filtered_by_campaign_and_status(engine: Engine) -> None:
    one, two = new_campaign(engine), new_campaign(engine, name="Other")
    youtube = account(engine)
    publish(engine, campaign_clip(engine, one.id), youtube, hour=1)
    publish(engine, campaign_clip(engine, two.id), youtube, hour=2)
    first = submissions.list_submissions(engine, one.id)
    move(engine, first[0].id, status="submitted")

    assert [s.campaign_id for s in submissions.list_submissions(engine)] == [
        two.id,
        one.id,
    ]
    assert [s.campaign_id for s in submissions.list_submissions(engine, two.id)] == [
        two.id
    ]
    submitted = submissions.list_submissions(engine, status="submitted")
    assert [s.campaign_id for s in submitted] == [one.id]


def test_copy_text_has_the_url_first_and_the_required_information(
    engine: Engine,
) -> None:
    campaign = new_campaign(engine)
    publish(engine, campaign_clip(engine, campaign.id), account(engine))

    lines = only(engine).copy_text.splitlines()

    assert lines[0] == URL
    assert lines[2:] == [
        "Campaign: Pizza Clips",
        "Platform: youtube",
        "Credit line: Clip of Chef Mario",
        "Hashtags: #pizza #clips",
        "Mentions: @chefmario",
        "Instructions: Paste the link in #submit",
    ]


def test_copy_text_leaves_out_what_the_campaign_does_not_require(
    engine: Engine,
) -> None:
    campaign = new_campaign(
        engine,
        required_credit_line="",
        required_hashtags=[],
        required_tags_mentions=[],
        submission_instructions="",
    )
    publish(engine, campaign_clip(engine, campaign.id), account(engine))

    assert (
        only(engine).copy_text == f"{URL}\n\nCampaign: Pizza Clips\nPlatform: youtube"
    )


def test_ticking_submitted_sets_the_date_and_unticking_clears_it(
    engine: Engine,
) -> None:
    publish(engine, campaign_clip(engine, new_campaign(engine).id), account(engine))
    view = only(engine)

    ticked = move(engine, view.id, status="submitted")
    assert ticked.status == "submitted"
    assert ticked.submitted_at is not None
    assert ticked.submitted_at.tzinfo is not None

    unticked = move(engine, view.id, status="not_submitted")
    assert (unticked.status, unticked.submitted_at) == ("not_submitted", None)


def test_the_status_machine_follows_the_board(engine: Engine) -> None:
    publish(engine, campaign_clip(engine, new_campaign(engine).id), account(engine))
    submission_id = only(engine).id

    for status in ("submitted", "rejected", "submitted", "approved", "paid"):
        assert move(engine, submission_id, status=status).status == status
    assert move(engine, submission_id, status="approved").status == "approved"


@pytest.mark.parametrize(
    ("old", "new"),
    [
        ("not_submitted", "approved"),
        ("not_submitted", "paid"),
        ("not_submitted", "rejected"),
        ("submitted", "paid"),
        ("rejected", "paid"),
        ("paid", "submitted"),
        ("paid", "rejected"),
    ],
)
def test_illegal_moves_are_refused_and_change_nothing(
    engine: Engine, old: str, new: str
) -> None:
    publish(engine, campaign_clip(engine, new_campaign(engine).id), account(engine))
    submission_id = only(engine).id
    path = {
        "not_submitted": [],
        "submitted": ["submitted"],
        "rejected": ["submitted", "rejected"],
        "paid": ["submitted", "approved", "paid"],
    }[old]
    for status in path:
        move(engine, submission_id, status=status)
    before = submissions.get_submission(engine, submission_id)

    with pytest.raises(IllegalSubmissionMove):
        move(engine, submission_id, status=new, notes="x", payout_usd=5)

    assert submissions.get_submission(engine, submission_id) == before


def test_views_payout_and_notes_are_kept_and_can_be_cleared(engine: Engine) -> None:
    publish(engine, campaign_clip(engine, new_campaign(engine).id), account(engine))
    submission_id = only(engine).id
    move(engine, submission_id, status="submitted")
    move(engine, submission_id, status="approved", approved_views=12000)

    paid = move(engine, submission_id, status="paid", payout_usd=18.5, notes="Wise")

    assert (paid.approved_views, paid.payout_usd, paid.notes) == (12000, 18.5, "Wise")
    cleared = move(engine, submission_id, payout_usd=None)
    assert (cleared.status, cleared.approved_views, cleared.payout_usd) == (
        "paid",
        12000,
        None,
    )
    assert cleared.notes == "Wise"


def test_a_patch_needs_a_field_and_no_negative_numbers() -> None:
    for body in ({}, {"status": None}, {"approved_views": -1}, {"payout_usd": -0.5}):
        with pytest.raises(ValueError):
            SubmissionPatch.model_validate(body)


def test_an_unknown_submission_is_not_found(engine: Engine) -> None:
    with pytest.raises(SubmissionNotFound):
        submissions.get_submission(engine, 99)
    with pytest.raises(SubmissionNotFound):
        move(engine, 99, notes="x")


def test_deleting_the_campaign_keeps_the_submission_with_its_payout(
    engine: Engine,
) -> None:
    campaign = new_campaign(engine)
    publish(engine, campaign_clip(engine, campaign.id), account(engine))
    submission_id = only(engine).id
    move(engine, submission_id, status="submitted")
    move(engine, submission_id, status="approved", approved_views=500)

    campaigns.delete_campaign(engine, campaign.id)

    kept = submissions.get_submission(engine, submission_id)
    assert (kept.campaign_id, kept.campaign_name, kept.approved_views) == (
        None,
        None,
        500,
    )
    assert kept.copy_text.splitlines()[0] == URL
