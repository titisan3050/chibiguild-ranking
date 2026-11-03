# ちびギルド放置録：ワールド全体ランキングの集計
#   ワールドから自動で届いた登録（Apps Script の受け口 ?csv=1）を読み、
#   登録コードを確かめて、1 人 1 件の最高記録にまとめ、docs/ranking.txt に書き出す。
#   ワールドはこのファイルを GitHub Pages から読み込んで表示する。
#
#   環境変数
#     AUTO_URL  自動登録の受け口（Apps Script のウェブアプリ …/exec）
import csv
import io
import os
import re
import sys
import urllib.request
from datetime import datetime, timedelta, timezone

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "docs", "ranking.txt")
TOP = 10
CODE_RE = re.compile(r"IGR1([0-9a-f.]+)-(\d{6})")

# ありえない値は弾く（ゲームの上限より少し広め）
LIMITS = {
    "atk": 400000,      # 攻撃力の桁 ×1000（10 の 400 乗まで）
    "kills": 9 * 10 ** 15,   # 総討伐数（2026-11-03 以前の登録では最高ステージだった）
    "tower": 100000,
    "rebirths": 1000000,
    "dragon": 10000000,
    "tier": 5,          # 5 強化天蛇ミズチ
    "tierKills": 99999,
}


def rank_check(body: str) -> int:
    """IGGame.RankCheck と同じ計算"""
    h = 7
    for ch in "chibiguild" + body:
        h = (h * 131 + ord(ch) + 17) % 1000003
    return h


def decode(code: str):
    m = CODE_RE.search(code)
    if not m:
        return None
    body, ck = m.group(1), int(m.group(2))
    if rank_check(body) != ck:
        return None
    f = body.split(".")
    # 削除コード：本文 = "0." + 名前（ワールドで「掲載 OFF」にして出したもの）
    is_del = len(f) == 2 and f[0] == "0"
    if not is_del and (len(f) != 9 or f[0] != "1"):
        return None
    hx = f[1]
    if len(hx) == 0 or len(hx) % 4 != 0:
        return None
    try:
        name = "".join(chr(int(hx[i:i + 4], 16)) for i in range(0, len(hx), 4))
        v = [int(x) for x in f[2:]]
    except ValueError:
        return None
    name = re.sub(r"[\t\r\n#]", " ", name).strip()[:32]
    if not name:
        return None
    if is_del:
        return name, None
    keys = ["atk", "kills", "tower", "rebirths", "dragon", "tier", "tierKills"]
    rec = dict(zip(keys, v))
    for k in keys:
        if rec[k] < 0 or rec[k] > LIMITS[k]:
            return None
    return name, rec


JST = timezone(timedelta(hours=9))
# この時刻より前の登録は、2 番目の数が「最高ステージ」だった（今は「総討伐数」）。古い登録の討伐数は 0 として扱う
KILLS_SINCE = datetime(2026, 11, 3, 7, 45, tzinfo=timezone.utc)


def row_time(cell: str):
    """フォームの「2026/11/03 13:08:53」（日本時間）と、自動登録の ISO 形式（UTC）を同じ物差しにする"""
    cell = cell.strip()
    for fmt in ("%Y/%m/%d %H:%M:%S", "%Y/%m/%d %H:%M"):
        try:
            return datetime.strptime(cell, fmt).replace(tzinfo=JST)
        except ValueError:
            pass
    try:
        return datetime.fromisoformat(cell.replace("Z", "+00:00"))
    except ValueError:
        return None


def fetch_csv(url: str):
    with urllib.request.urlopen(url, timeout=30) as r:
        text = r.read().decode("utf-8-sig")
    return list(csv.reader(io.StringIO(text)))


def main():
    auto = os.environ.get("AUTO_URL", "").strip()
    rows = []
    if len(sys.argv) > 1:
        # 手元で試すとき：python build_ranking.py 自動登録.csv
        for path in sys.argv[1:]:
            with open(path, encoding="utf-8-sig") as fp:
                rows += list(csv.reader(fp))[1:]
    elif not auto:
        print("AUTO_URL が設定されていない", file=sys.stderr)
    if auto:
        # 自動登録の受け口（Apps Script）。?csv=1 で「time,code」を返す
        try:
            rows += fetch_csv(auto + ("&" if "?" in auto else "?") + "csv=1")[1:]
        except Exception as ex:  # 受け口が止まっていても、フォームの分は集計する
            print("自動登録を読めなかった:", ex, file=sys.stderr)
    # 送られた順に処理する（削除のあとに登録し直した人は、また載る）
    far = datetime(1970, 1, 1, tzinfo=timezone.utc)
    rows = [r for r in rows if r]
    rows.sort(key=lambda r: row_time(r[0]) or far)

    best = {}
    ok = bad = removed = 0
    for row in rows:
        found = False
        for cell in row:
            d = decode(cell.replace(" ", "").replace("\n", ""))
            if d is None:
                continue
            found = True
            name, rec = d
            if rec is None:
                # 削除コード：それまでの記録を消す（あとで登録し直せばまた載る）
                best.pop(name, None)
                removed += 1
                break
            t = row_time(row[0])
            # 古いワールドのままの人は、この欄に最高ステージ（120 まで）を入れて送ってくる。討伐数としては数えない
            if t is None or t < KILLS_SINCE or rec["kills"] <= 120:
                rec["kills"] = 0
            b = best.setdefault(name, {k: 0 for k in rec})
            for k in ("atk", "kills", "tower", "rebirths", "dragon"):
                b[k] = max(b[k], rec[k])
            # 竜の格は「格 × 100000 + その討伐数」で比べる
            b["raid"] = max(b.get("raid", 0), rec["tier"] * 100000 + rec["tierKills"])
            ok += 1
            break
        if not found and any("IGR1" in c for c in row):
            bad += 1

    cats = ["atk", "kills", "tower", "rebirths", "dragon", "raid"]
    jst = timezone(timedelta(hours=9))
    lines = [
        "#updated " + datetime.now(jst).strftime("%Y-%m-%d %H:%M") + " JST",
        "#players " + str(len(best)),
    ]
    for ci, k in enumerate(cats):
        items = [(n, b.get(k, 0)) for n, b in best.items() if b.get(k, 0) > 0]
        items.sort(key=lambda x: (-x[1], x[0]))
        for n, v in items[:TOP]:
            lines.append(f"{ci}\t{n}\t{v}")
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    # 中身が前と同じなら書き換えない（5 分ごとに動くので、変わったときだけ保存する）。
    # ただし 1 日 1 回は更新時刻を書き直す（長く更新がないと GitHub が定期実行を止めるため）
    try:
        with open(OUT, encoding="utf-8") as fp:
            old = fp.read().splitlines()
    except FileNotFoundError:
        old = []
    old_body = [l for l in old if not l.startswith("#updated ")]
    new_body = [l for l in lines if not l.startswith("#updated ")]
    old_day = next((l[9:19] for l in old if l.startswith("#updated ")), "")
    if old_body == new_body and old_day == lines[0][9:19]:
        print(f"unchanged players={len(best)} codes_ok={ok} removed={removed} codes_bad={bad}")
        return
    with open(OUT, "w", encoding="utf-8", newline="\n") as fp:
        fp.write("\n".join(lines) + "\n")
    print(f"players={len(best)} codes_ok={ok} removed={removed} codes_bad={bad} -> {OUT}")


if __name__ == "__main__":
    main()
