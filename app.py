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
YOUR_USER_ID = st.secrets["YOUR_USER_ID"]
NUM_WINNERS = 10
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
def get_followers(user_id: str) -> set:
"""指定ユーザーのフォロワーIDを全取得"""
ids = set()
pagination_token = None
while True:
resp = client.get_users_followers(
user_id, max_results=1000, pagination_token=pagination_token
)
if resp.data:
ids.update(u.id for u in resp.data)
if not resp.meta or "next_token" not in resp.meta:
break
pagination_token = resp.meta["next_token"]
return ids
def get_user_details(user_ids: list) -> list:
"""ユーザーIDからプロフィール情報を取得（100件ずつ）"""
all_users = []
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
st.caption("リポスト × フォロー × 特定ワードのリプライ — 全条件を満たした方から抽選します")
st.divider()
# --- 入力フォーム ---
tweet_url = st.text_input(
"📌 募集ツイートのURL",
placeholder="https://x.com/username/status/1234567890",
)
keyword = st.text_input(
"🔑 リプライに含むべきキーワード",
placeholder="例: 参加します",
)
st.divider()
# --- 抽選実行 ---
if st.button("🎲 抽選を実行する", type="primary", use_container_width=True):
# バリデーション
tweet_id = extract_tweet_id(tweet_url)
if not tweet_id:
st.error("❌ 有効なツイートURLを入力してください")
st.stop()
if not keyword.strip():
st.error("❌ キーワードを入力してください")
st.stop()
# 1) ツイート投稿者を取得
with st.spinner("ツイート情報を取得中..."):
author_id = get_tweet_author(tweet_id)
if not author_id:
st.error("❌ ツイートが見つかりません。URLを確認してください。")
st.stop()
author_info = client.get_user(id=author_id)
author_username = author_info.data.username if author_info.data else "unknown"
st.info(f"📣 ツイート投稿者: **@{author_username}**")
# 2) リポストしたユーザーを取得
with st.spinner("リポストしたユーザーを取得中..."):
retweeters = get_retweeters(tweet_id)
st.info(f"🔁 リポスト: **{len(retweeters)}** 人")
# 3) キーワード付きリプライしたユーザーを取得
with st.spinner(f'「{keyword}」を含むリプライを取得中...'):
repliers = get_repliers_with_keyword(tweet_id, keyword.strip())
st.info(f'💬 「{keyword}」を含むリプライ: **{len(repliers)}** 人')
# 4) ツイート投稿者のフォロワーを取得
with st.spinner(f"@{author_username} のフォロワーを取得中...（フォロワー数により時間がかかる場合があります）"):
followers = get_followers(author_id)
st.info(f"👥 フォロワー: **{len(followers)}** 人")
# 5) 全条件の積集合
eligible = retweeters & repliers & followers
st.divider()
if len(eligible) == 0:
st.warning("⚠️ 全条件を満たすユーザーが見つかりませんでした")
st.markdown("**内訳を確認してください:**")
st.markdown(f"- リポスト ∩ リプライ（キーワード含む）: **{len(retweeters & repliers)}** 人")
st.markdown(f"- リポスト ∩ フォロー: **{len(retweeters & followers)}** 人")
st.markdown(f"- リプライ ∩ フォロー: **{len(repliers & followers)}** 人")
st.stop()
st.success(f"✅ **全条件クリア: {len(eligible)} 人**")
# 6) ランダム抽選
seed = int(datetime.now().timestamp() * 1000)
random.seed(seed)
winner_ids = random.sample(list(eligible), min(NUM_WINNERS, len(eligible)))
# 7) 当選者の詳細情報を取得
with st.spinner("当選者情報を取得中..."):
winners = get_user_details(winner_ids)
# 8) 結果表示
st.divider()
st.header("🎉 当選者")
for i, user in enumerate(winners, 1):
col1, col2 = st.columns([1, 10])
with col1:
st.markdown(f"### {i}")
with col2:
st.markdown(f"**@{user.username}**（{user.name}）")
st.markdown(f"[プロフィールを見る](https://x.com/{user.username})")
st.divider()
# 9) メタ情報
st.divider()
st.caption("📋 抽選メタ情報（公正性の証明用）")
st.code(
f"抽選日時: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
f"シード値: {seed}\n"
f"対象ツイート: {tweet_url}\n"
f"キーワード: {keyword}\n"
f"全条件クリア: {len(eligible)}人\n"
f"当選者数: {len(winners)}人",
language=None,
)
