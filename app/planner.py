"""Guard against the retired shared-card auto-planning workflow.

Kai weekly copy and every tarot image are created and reviewed outside the
repository.  GitHub receives only approved post data and finished images.
"""


CARDS = ()


def plan(seed=None):
    del seed
    raise RuntimeError(
        "旧カード素材を使う自動企画は廃止済みです。"
        "承認済みの週次投稿データと新規制作済み完成画像を投入してください。"
    )
