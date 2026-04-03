import streamlit as st
import tweepy
import random
import re
from datetime import datetime

# ============================================================
# 設定（Streamlit Cloud の Secrets から読み込み）
# ============================================================
BEARER_TOKEN = st.secrets["BEARER_TOKEN"]
NUM_WINNERS = 10

# APIリクエスト回数を最小限にする設定
client = tweepy.Client(bearer_token=BEARER_TOKEN, wait_on_rate_limit=True)

# ============================================================
# ユーティリティ関数（コスト最小化版）
# ============================================================
def extract_tweet_id(url: str) -> str | None:
    match = re.search(r"/status/(\d+)", url)
    return match.group(1) if match else None

def get_retweeters(tweet_id: str) -> set:
    """リポストしたユーザーIDを取得（100件ずつ一括取得）"""
    ids = set()
    pagination_token = None
    try:
        while True:
            resp = client.get_retweeters(tweet_id, max_results=100, pagination_token=pagination_token)
            if resp.data:
                ids.update(u.id for u in resp.data)
            if not resp.meta or "next_token" not in resp.meta:
                break
            pagination_token = resp.meta["next_token"]
    except Exception as e:
        st.error(f"リポスト取得エラー: {e}")
    return ids

def get_repliers_with_keyword(tweet_id: str, keyword: str) -> set:
    """リプライを全取得し、特殊文字や改行を無視してキーワード判定を行う"""
    ids = set()
    pagination_token = None
    
    # 判定用の正規表現：キーワードの各文字の間に「0個以上の任意の文字（空白や改行含む）」を許容する
    # 例: 「クリスタ」なら「ク.*リ.*ス.*タ」のようなパターンを作る
    pattern = ".*".join(map(re.escape, keyword))
    
    try:
        while True:
            # 検索クエリからはキーワードを外し、リプライを全件持ってくる（これが確実）
            query = f'conversation_id:{tweet_id} is:reply'
            resp = client.search_recent_tweets(
                query=query, 
                max_results=100, 
                tweet_fields=["author_id", "text"], # text（本文）を取得して判定に使う
                pagination_token=pagination_token
            )
            
            if resp.data:
                for t in resp.data:
                    # 本文から改行や特殊な空白を除去してから判定、
                    # または正規表現で「あいまいに」マッチさせる
                    if re.search(pattern, t.text):
                        ids.update([t.author_id])
                        
            if not resp.meta or "next_token" not in resp.meta:
                break
            pagination_token = resp.meta["next_token"]
            
    except Exception as e:
        st.error(f"リプライ取得エラー: {e}")
        
    return ids

def get_user_details(user_ids: list) -> list:
    """100人一括でプロフィール取得（リクエスト数を最小化）"""
    all_users = []
    if not user_ids: return all_users
    for i in range(0, len(user_ids), 100):
        chunk = user_ids[i : i + 100]
        try:
            resp = client.get_users(ids=chunk, user_fields=["username", "name"])
            if resp.data:
                all_users.extend(resp.data)
        except Exception:
            continue
    return all_users

# ============================================================
# UI
# ============================================================
st.set_page_config(page_title="最安抽選ツール", page_icon="💰")
st.title("💰 節約版・X抽選ツール")
st.caption("リポストとリプライのみAPIで抽出し、フォローは目視で確認します（API代を節約）")

tweet_url = st.text_input("📌 募集ツイートURL")
keyword = st.text_input("🔑 キーワード", value="クリスタのモニター")

if st.button("🎲 抽選を実行（低コスト）", type="primary", use_container_width=True):
    tweet_id = extract_tweet_id(tweet_url)
    if not tweet_id:
        st.error("URLが正しくありません")
        st.stop()

    # 1) データ取得（一括取得のみ）
    with st.spinner("データを取得中..."):
        retweeters = get_retweeters(tweet_id)
        repliers = get_repliers_with_keyword(tweet_id, keyword)
    
    # 2) 積集合（リポスト ∩ リプライ）
    candidates = list(retweeters & repliers)
    
    st.success(f"✅ 候補者: {len(candidates)} 人 (リポスト & リプライ済み)")

    if not candidates:
        st.warning("条件に合う人がいません")
        st.stop()

    # 3) ランダム抽選
    winners_list = random.sample(candidates, min(NUM_WINNERS, len(candidates)))

    # 4) 当選者情報の表示
    with st.spinner("当選者プロフィールを取得中..."):
        winners = get_user_details(winners_list)

    st.divider()
    st.header("🎉 当選候補（要フォロー確認）")
    st.info("以下のユーザーがフォローしてくれているか、ボタンから確認してください。")

    for i, user in enumerate(winners, 1):
        c1, c2 = st.columns([7, 3])
        with c1:
            st.markdown(f"**{i}. @{user.username}** ({user.name})")
        with c2:
            # 直接プロフィールのフォロー状況を確認できるリンクボタン
            st.link_button("👤 フォロー確認", f"https://x.com/{user.username}")
        st.divider()

    # 5) メタ情報
    st.caption(f"抽選日時: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
