import streamlit as st
import tweepy
import random
import re
import time
from datetime import datetime

# ============================================================
# 設定（Streamlit Cloud の Secrets から読み込み）
# ============================================================
BEARER_TOKEN = st.secrets["BEARER_TOKEN"]
NUM_WINNERS = 10

# wait_on_rate_limit=True でレートリミット時に自動待機
client = tweepy.Client(bearer_token=BEARER_TOKEN, wait_on_rate_limit=True)

# ============================================================
# ユーティリティ関数
# ============================================================
def extract_tweet_id(url: str) -> str | None:
    """ツイートURLからIDを抽出"""
    match = re.search(r"/status/(\d+)", url)
    return match.group(1) if match else None

def get_tweet_author(tweet_id: str) -> str | None:
    """ツイートの投稿者ユーザーIDを取得"""
    resp = client.get_tweet(tweet_id, tweet_fields=["author_id"])
    if resp.data:
        return resp.data.author_id
    return None

def get_retweeters(tweet_id: str) -> set:
    """リポスト（リツイート）したユーザーIDを全取得"""
    ids = set()
    pagination_token = None
    while True:
        resp = client.get_retweeters(
            tweet_id, max_results=100, pagination_token=pagination_token
        )
        if resp.data:
            ids.update(u.id for u in resp.data)
        if not resp.meta or "next_token" not in resp.meta:
            break
        pagination_token = resp.meta["next_token"]
    return ids

def get_repliers_with_keyword(tweet_id: str, keyword: str) -> set:
    """特定キーワードを含むリプライをしたユーザーIDを全取得"""
    ids = set()
    pagination_token = None
    while True:
        # conversation_id でスレッド内を検索し、キーワードで絞り込み
        query = f'conversation_id:{tweet_id} is:reply "{keyword}"'
        resp = client.search_recent_tweets(
            query=query,
            max_results=100,
            tweet_fields=["author_id"],
            pagination_token=pagination_token,
        )
        if resp.data:
            ids.update(t.author_id for t in resp.data)
        if not resp.meta or "next_token" not in resp.meta:
            break
        pagination_token = resp.meta["next_token"]
    return ids

def check_is_following(user_id: str, target_author_id: str) -> bool:
    """ユーザーがポスト主をフォローしているか確認 (個別に判定)"""
    try:
        # ユーザーがフォローしている一覧のなかに target_author_id が含まれるか確認
        # ※このエンドポイントは1人ずつ確認する際に403エラーが出にくい傾向にあります
        resp = client.get_users_following(id=user_id, max_results=1000)
        if resp.data:
            following_ids = [u.id for u in resp.data]
            return target_author_id in following_ids
    except Exception as e:
        # 鍵垢などの場合は取得できないため False
        return False
    return False

def get_user_details(user_ids: list) -> list:
    """ユーザーIDからプロフィール情報を取得（100件ずつ）"""
    all_users = []
    if not user_ids:
        return all_users
    for i in range(0, len(user_ids), 100):
        chunk = user_ids[i : i + 100]
        resp = client.get_users(
            ids=chunk, user_fields=["username", "name", "profile_image_url"]
        )
        if resp.data:
            all_users.extend(resp.data)
    return all_users

# ============================================================
# UI
# ============================================================
st.set_page_config(page_title="X 抽選ツール", page_icon="🎰", layout="centered")

st.title("🎰 X（Twitter）抽選ツール")
st.caption("リポスト × フォロー × 特定ワードのリプライ — 条件を満たした方から抽選します")

st.divider()

tweet_url = st.text_input(
    "📌 募集ツイートのURL",
    placeholder="https://x.com/username/status/1234567890",
)
keyword = st.text_input(
    "🔑 リプライに含むべきキーワード",
    placeholder="例: クリスタのモニター",
)

st.divider()

if st.button("🎲 抽選を実行する", type="primary", use_container_width=True):

    tweet_id = extract_tweet_id(tweet_url)
    if not tweet_id or not keyword.strip():
        st.error("❌ URLとキーワードを正しく入力してください")
        st.stop()

    # 1) ツイート投稿者を取得
    with st.spinner("ツイート情報を取得中..."):
        author_id = get_tweet_author(tweet_id)
        if not author_id:
            st.error("❌ ツイートが見つかりません。")
            st.stop()
        author_info = client.get_user(id=author_id)
        author_username = author_info.data.username if author_info.data else "unknown"
        st.info(f"📣 ポスト主: **@{author_username}**")

    # 2) リポストしたユーザーを取得
    with st.spinner("リポストしたユーザーを取得中..."):
        retweeters = get_retweeters(tweet_id)
    st.info(f"🔁 リポスト: **{len(retweeters)}** 人")

    # 3) キーワード付きリプライしたユーザーを取得
    with st.spinner(f'「{keyword}」を含むリプライを取得中...'):
        repliers = get_repliers_with_keyword(tweet_id, keyword.strip())
    st.info(f'💬 指定ワードのリプライ: **{len(repliers)}** 人')

    # 4) 条件を重ねる（リポスト かつ リプライ）
    # まずはフォロワー判定以外で絞り込む
    candidates = retweeters & repliers
    st.info(f"📍 リポスト＋リプライ済み: **{len(candidates)}** 人")

    # 5) フォロー判定（候補者に対してのみ実行）
    final_eligible = []
    if len(candidates) > 0:
        progress_text = "フォロー状況を最終確認中..."
        my_bar = st.progress(0, text=progress_text)
        
        for i, user_id in enumerate(candidates):
            # 1人ずつフォロー判定
            if check_is_following(user_id, author_id):
                final_eligible.append(user_id)
            
            # 進捗表示
            progress = (i + 1) / len(candidates)
            my_bar.progress(progress, text=f"{progress_text} ({i+1}/{len(candidates)})")
            # API負荷軽減のためわずかに待機（必要に応じて調整）
            time.sleep(0.1)
        my_bar.empty()

    st.success(f"✅ **全条件クリア（フォロー含む）: {len(final_eligible)} 人**")

    if len(final_eligible) == 0:
        st.warning("⚠️ 全条件を満たすユーザーが見つかりませんでした")
        st.stop()

    # 6) ランダム抽選
    seed = int(datetime.now().timestamp() * 1000)
    random.seed(seed)
    winner_ids = random.seed(seed) # 不要な重複削除のため修正
    winners_list = random.sample(final_eligible, min(NUM_WINNERS, len(final_eligible)))

    # 7) 当選者の詳細情報を取得
    with st.spinner("当選者情報を取得中..."):
        winners = get_user_details(winners_list)

    # 8) 結果表示
    st.divider()
    st.header("🎉 当選者一覧")

    for i, user in enumerate(winners, 1):
        col1, col2 = st.columns([1, 10])
        with col1:
            st.markdown(f"### {i}")
        with col2:
            st.markdown(f"**@{user.username}**（{user.name}）")
            st.markdown(f"[プロフィールを見る](https://x.com/{user.username})")
        st.divider()

    # 9) メタ情報
    st.caption("📋 抽選メタ情報")
    st.code(
        f"抽選日時: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"シード値: {seed}\n"
        f"対象人数: {len(final_eligible)}人",
        language=None,
    )
