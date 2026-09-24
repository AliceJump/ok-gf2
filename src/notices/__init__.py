"""Local notices and their shared acknowledgement state."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Notice:
    id: str
    title: str
    task: str
    solution: str
    url: str
    active: bool = True


NOTICES = (
    Notice(
        id="drink-route-issue-78",
        title="喝水任务可能因移动受阻而失败",
        task="喝水",
        solution="请检查并调整「喝水」移动时长，参考 1.087-1.0-0.8",
        url="https://github.com/AliceJump/ok-gf2/issues/78",
    ),
)


def unread_notices(read_ids: set[str], notices=NOTICES) -> list[Notice]:
    return [notice for notice in notices if notice.active and notice.id not in read_ids]
