"""The connected social accounts (SPEC-v2 3.10, 4): one SocialAccount row per
(platform, external_id), its token in the encrypted token store under the
row's token_ref. A platform may have several accounts."""

from datetime import UTC, datetime

from sqlalchemy import Engine
from sqlmodel import Session, col, func, select

from clipforge.models import PostStatus, SocialAccount, SocialPlatform
from clipforge.oauth_tokens import Token
from clipforge.publishers.base import AccountProfile
from clipforge.social_rows import PostRow, SocialAccountRow
from clipforge.token_store import TokenStore

# Posts in these states still need their account: it cannot be disconnected.
PENDING_POST_STATUSES: tuple[PostStatus, ...] = ("draft", "queued", "uploading")


class AccountNotFound(LookupError):
    """There is no such account."""


class AccountBusy(Exception):
    """The account still has posts to publish."""


def save_account(
    engine: Engine,
    store: TokenStore,
    platform: SocialPlatform,
    profile: AccountProfile,
    token: Token,
    token_ref: str,
    scopes: list[str],
) -> SocialAccount:
    """Store a signed-in account, the scopes it granted and its token. The
    same account (platform and external_id) connected again keeps its row
    and token_ref and gets the new token, name, picture, scopes and
    restrictions; a new one gets token_ref, and becomes the platform's
    default account if it has none."""
    with Session(engine) as session:
        row = session.exec(
            select(SocialAccountRow).where(
                col(SocialAccountRow.platform) == platform,
                col(SocialAccountRow.external_id) == profile.external_id,
            )
        ).first()
        if row is None:
            row = SocialAccountRow(
                platform=platform, external_id=profile.external_id, token_ref=token_ref
            )
        row.display_name = profile.display_name
        row.avatar_url = _avatar(profile.avatar_url)
        row.scopes = scopes
        row.restrictions = list(profile.restrictions)
        row.connected_at = datetime.now(UTC)
        if row.id is None and not _has_default(session, platform):
            row.is_default = True
        session.add(row)
        session.commit()
        session.refresh(row)
        account = row.to_model()
    store.save(account.token_ref, token)
    return account


def list_accounts(
    engine: Engine, platform: SocialPlatform | None = None
) -> list[SocialAccount]:
    """Return the connected accounts (of platform, if given), oldest first."""
    query = select(SocialAccountRow).order_by(col(SocialAccountRow.id))
    if platform is not None:
        query = query.where(col(SocialAccountRow.platform) == platform)
    with Session(engine) as session:
        return [row.to_model() for row in session.exec(query)]


def get_account(engine: Engine, account_id: int) -> SocialAccount:
    """Return the account; AccountNotFound if there is none."""
    with Session(engine) as session:
        row = session.get(SocialAccountRow, account_id)
        if row is None:
            raise AccountNotFound(f"account {account_id} does not exist")
        return row.to_model()


def default_account(engine: Engine, platform: SocialPlatform) -> SocialAccount | None:
    """Return the account that a one-click post uses on platform, or None."""
    with Session(engine) as session:
        row = session.exec(
            select(SocialAccountRow).where(
                col(SocialAccountRow.platform) == platform,
                col(SocialAccountRow.is_default),
            )
        ).first()
        return row.to_model() if row is not None else None


def set_default(engine: Engine, account_id: int) -> SocialAccount:
    """Make the account the default of its platform (the platform's other
    accounts stop being it) and return it; AccountNotFound if there is
    none."""
    with Session(engine) as session:
        row = session.get(SocialAccountRow, account_id)
        if row is None:
            raise AccountNotFound(f"account {account_id} does not exist")
        for other in session.exec(
            select(SocialAccountRow).where(
                col(SocialAccountRow.platform) == row.platform,
                col(SocialAccountRow.id) != account_id,
                col(SocialAccountRow.is_default),
            )
        ):
            other.is_default = False
            session.add(other)
        row.is_default = True
        session.add(row)
        session.commit()
        session.refresh(row)
        return row.to_model()


def set_always_hashtags(
    engine: Engine, account_id: int, hashtags: list[str]
) -> SocialAccount:
    """Set the hashtags that every generated post to the account carries
    and return it; AccountNotFound if there is none."""
    with Session(engine) as session:
        row = session.get(SocialAccountRow, account_id)
        if row is None:
            raise AccountNotFound(f"account {account_id} does not exist")
        row.always_hashtags = hashtags
        session.add(row)
        session.commit()
        session.refresh(row)
        return row.to_model()


def disconnect(engine: Engine, store: TokenStore, account_id: int) -> None:
    """Forget the account and its token on this machine; its finished posts
    stay (without an account). AccountNotFound if there is none; AccountBusy
    while it has posts in PENDING_POST_STATUSES (cancel them first). The
    oldest other account of its platform takes over as the default."""
    with Session(engine) as session:
        row = session.get(SocialAccountRow, account_id)
        if row is None:
            raise AccountNotFound(f"account {account_id} does not exist")
        pending = session.exec(
            select(func.count())
            .select_from(PostRow)
            .where(
                col(PostRow.account_id) == account_id,
                col(PostRow.status).in_(PENDING_POST_STATUSES),
            )
        ).one()
        if pending:
            raise AccountBusy(
                f"{row.display_name or 'This account'} has {pending} post(s) "
                "waiting to be published; cancel them before disconnecting."
            )
        token_ref, platform, was_default = row.token_ref, row.platform, row.is_default
        session.delete(row)
        if was_default:
            heir = session.exec(
                select(SocialAccountRow)
                .where(col(SocialAccountRow.platform) == platform)
                .order_by(col(SocialAccountRow.id))
            ).first()
            if heir is not None:
                heir.is_default = True
                session.add(heir)
        session.commit()
    store.delete(token_ref)


def _has_default(session: Session, platform: SocialPlatform) -> bool:
    """Whether platform has a default account."""
    return (
        session.exec(
            select(SocialAccountRow.id).where(
                col(SocialAccountRow.platform) == platform,
                col(SocialAccountRow.is_default),
            )
        ).first()
        is not None
    )


def _avatar(url: str | None) -> str | None:
    """Return url if it is an https link (the UI shows it as an image)."""
    return url if url and url.startswith("https://") else None
