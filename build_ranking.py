# ちびギルド放置録：ワールド全体ランキングの集計
#   ワールドから自動で届いた登録（Apps Script の受け口 ?csv=1）を読み、
#   登録コードを確かめて、1 人 1 件の最高記録にまとめ、docs/ranking.txt に書き出す。
#   ワールドはこのファイルを GitHub Pages から読み込んで表示する。
#
#   ギルド：種類 3 の登録にはギルドの値が付く。ギルドID ごとに束ね、週ごとのギルドランキングと
#   先週の確定結果（順位・報酬を受け取れる人）を ranking.txt に足す。週をまたいで残す値は state/guilds.json に保存する
#
#   環境変数
#     AUTO_URL  自動登録の受け口（Apps Script のウェブアプリ …/exec）
import csv
import io
import json
import os
import re
import sys
import urllib.request
from datetime import datetime, timedelta, timezone

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "docs", "ranking.txt")
STATE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "state", "guilds.json")
GUILD_MAX = 20          # 1 ギルドの人数の上限
WEEK_CAP = 1000000      # 1 人 1 週の貢献の上限はない。これを超える値だけは、ありえない値としてはじく
REWARD_TOP = 30         # 報酬が出る順位
TOP = 10
CODE_RE = re.compile(r"IGR1([0-9a-f.]+)-(\d{6})")

# ありえない値は弾く（ゲームの上限より少し広め）
LIMITS = {
    "atk": 400000,      # 攻撃力の桁 ×1000（10 の 400 乗まで）
    "kills": 9 * 10 ** 15,   # 総討伐数（2026-11-03 以前の登録では最高ステージだった）
    "tower": 100000,
    "rebirths": 1000000,
    "dragon": 10000000,
    "tier": 9,          # 5 強化天蛇ミズチ・6 究極天蛇ミズチ・7 ツクヨミ・8 強化・9 究極
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
    is_guild = len(f) in (20, 21) and f[0] == "3"
    if not is_del and not is_guild and (len(f) != 9 or f[0] != "1"):
        return None
    hx = f[1]
    if len(hx) == 0 or len(hx) % 4 != 0:
        return None
    try:
        name = "".join(chr(int(hx[i:i + 4], 16)) for i in range(0, len(hx), 4))
        v = [int(x) for x in f[2:9]] if not is_del else []
        guild = None
        if is_guild:
            g = [int(x) for x in f[9:19]]
            gh = f[19]
            if len(gh) % 4 != 0:
                return None
            gname = "".join(chr(int(gh[i:i + 4], 16)) for i in range(0, len(gh), 4))
            guild = dict(zip(["gid", "kc", "role", "ver", "emblem", "week", "wp", "lweek", "lwp", "total"], g))
            dh = f[20] if len(f) == 21 else ""
            if len(dh) % 7 != 0:
                return None
            guild["dec"] = [(int(dh[i], 16), int(dh[i + 1:i + 7], 16)) for i in range(0, len(dh), 7)]
            guild["name"] = re.sub(r"[\t\r\n#]", " ", gname).strip()[:8]
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
    if guild is not None:
        if not (0 < guild["gid"] < 2 ** 31 and 0 <= guild["role"] <= 3 and 0 <= guild["emblem"] < 144):
            guild = None
    rec["guild"] = guild
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


def name_hash(name: str) -> int:
    """IGGuild.NameHash と同じ（C# の文字＝UTF-16 の単位で数える）"""
    u = name.encode("utf-16-le")
    h = 7
    for i in range(0, len(u), 2):
        h = (h * 131 + (u[i] | (u[i + 1] << 8)) + 17) % 2000003
    return h


def week_now() -> int:
    return (datetime.now(JST).date().toordinal() - 1) // 7


def load_state():
    try:
        with open(STATE, encoding="utf-8") as fp:
            return json.load(fp)
    except (FileNotFoundError, ValueError):
        return {}


def guild_lines(latest: dict, state: dict):
    """latest = 名前 → その人の最新のギルドの値（無所属なら None）。ranking.txt に足す行を返す"""
    W = week_now()
    state.setdefault("launch", W)
    since = state.setdefault("since", {})
    weeks = state.setdefault("weeks", {})
    finals = state.setdefault("finals", {})
    approved = state.setdefault("approved", {})   # ギルドID → 承認された人（合言葉なしでもメンバー）
    rejected = state.setdefault("rejected", {})   # ギルドID → {見送られた人: 週}

    # ---- ギルドID ごとに束ねる。合言葉の検査値が食い違うときは、人数の多い方を正しいとする。役職 0 は申請中 ----
    groups, apps = {}, {}
    for name, g in latest.items():
        if not g:
            continue
        if g["role"] == 0:
            apps.setdefault(g["gid"], []).append(name)
        else:
            groups.setdefault(g["gid"], {}).setdefault(g["kc"], []).append(name)
    members = {}
    for gid, by_kc in groups.items():
        best_kc = max(by_kc, key=lambda kc: (len(by_kc[kc]), any(latest[n]["role"] == 3 for n in by_kc[kc])))
        members[gid] = list(by_kc[best_kc])
    # 加入申請への判断：マスター・副マスターが送った名前の検査値を、申請中の人と照らし合わせる
    for gid, names in members.items():
        for n in names:
            g = latest[n]
            if g["role"] < 2:
                continue
            for flag, h in g.get("dec", []):
                for a in apps.get(gid, []):
                    if name_hash(a) != h:
                        continue
                    if flag == 1:
                        lst = approved.setdefault(str(gid), [])
                        if a not in lst:
                            lst.append(a)
                        rejected.get(str(gid), {}).pop(a, None)
                    elif a not in approved.get(str(gid), []):
                        rejected.setdefault(str(gid), {})[a] = W
    # 承認された人は、最新の登録が同じギルドを指している間はメンバー（ほかへ移ったら外す）
    for sg in list(approved):
        gid = int(sg)
        keep = [n for n in approved[sg] if latest.get(n) and latest[n]["gid"] == gid and gid in members]
        for n in keep:
            if n not in members[gid]:
                members[gid].append(n)
        if keep:
            approved[sg] = keep
        else:
            del approved[sg]
    for sg in list(rejected):
        for n in [n for n, wk in rejected[sg].items() if wk < W - 2]:
            del rejected[sg][n]
        if not rejected[sg]:
            del rejected[sg]
    for gid, names in members.items():
        # 加入した週（集計が初めて見た週）を記録する。始めた週に入っていた人は、その前から居たことにする
        for n in names:
            cur = since.get(n)
            if not cur or cur[0] != gid:
                since[n] = [gid, W - 1 if W == state["launch"] else W]
        names.sort(key=lambda n: (since[n][1], n))
        members[gid] = names[:GUILD_MAX]
    # どのギルドにもいなくなった人は記録から外す
    valid = {n for ns in members.values() for n in ns}
    for n in list(since):
        if n not in valid:
            del since[n]

    # ---- 週ごとの貢献を残す（今週・先週）。同じ週の値は大きい方 ----
    def put(week, name, pts, gid):
        wk = weeks.setdefault(str(week), {})
        pts = max(0, min(pts, WEEK_CAP))
        old = wk.get(name)
        if not old or old[1] != gid or pts > old[0]:
            wk[name] = [max(pts, old[0]) if old and old[1] == gid else pts, gid]

    for gid, names in members.items():
        for n in names:
            g = latest[n]
            if g["week"] in (W, W - 1):
                put(g["week"], n, g["wp"], gid)
            if g["lweek"] == W - 1:
                put(W - 1, n, g["lwp"], gid)

    # ---- ギルドの名前と紋章：マスターの最新の版。いなければ版のいちばん新しい人 ----
    info = {}
    for gid, names in members.items():
        rows = sorted((latest[n] for n in names), key=lambda g: (g["role"] == 3 and g["name"] != "", g["ver"]), reverse=True)
        top = rows[0]
        nm = next((g["name"] for g in rows if g["name"] and g["name"] != "名無しのギルド"), "")
        master = next((n for n in names if latest[n]["role"] == 3), "")
        info[gid] = {"name": nm, "emblem": top["emblem"], "total": sum(latest[n]["total"] for n in names), "master": master}

    def scores(week):
        sc = {}
        for n, (pts, gid) in weeks.get(str(week), {}).items():
            sc[gid] = sc.get(gid, 0) + pts
        return sc

    # ---- 先週の確定（1 回だけ。あとから届いた値では変えない） ----
    F = W - 1
    if str(F) not in finals:
        sc = scores(F)
        order = sorted((g for g in sc if sc[g] > 0), key=lambda g: (-sc[g], g))
        prev = finals.get(str(F - 1))
        streak = 1
        if order and prev and prev.get("ranks") and prev["ranks"][0][0] == order[0]:
            streak = prev.get("streak", 1) + 1
        ranks, elig = [], {}
        for i, gid in enumerate(order[:REWARD_TOP]):
            meta = info.get(gid) or (prev or {}).get("info", {}).get(str(gid)) or {"name": "", "emblem": 0}
            ranks.append([gid, i + 1, sc[gid], meta["name"], meta["emblem"]])
            elig[str(gid)] = sorted(n for n, (pts, g) in weeks.get(str(F), {}).items()
                                    if g == gid and pts >= 1 and n in since and since[n][0] == gid and since[n][1] < F)
        finals[str(F)] = {"ranks": ranks, "eligible": elig, "streak": streak if order else 0}

    # 古い週は消す
    for k in list(weeks):
        if int(k) < W - 3:
            del weeks[k]
    for k in list(finals):
        if int(k) < W - 6:
            del finals[k]

    # ---- 書き出し ----
    cur = scores(W)
    lines = ["#gseason " + str(W)]
    order = sorted(members, key=lambda g: (-cur.get(g, 0), -info[g]["total"], g))
    for gid in order:
        m = info[gid]
        lines.append(f"g\t{gid}\t{m['name']}\t{m['emblem']}\t{cur.get(gid, 0)}\t{len(members[gid])}\t{m['total']}\t{m['master']}")
    for gid in order:
        wk = weeks.get(str(W), {})
        for n in members[gid]:
            lines.append(f"m\t{gid}\t{n}\t{max(1, latest[n]['role'])}\t{wk.get(n, [0, 0])[0]}")
    # 加入申請：まだ判断されていない申請（a）と、見送られた申請（r）
    for gid in order:
        ok = set(approved.get(str(gid), []))
        rj = rejected.get(str(gid), {})
        for a in sorted(apps.get(gid, [])):
            if a not in ok and a not in rj:
                lines.append(f"a\t{gid}\t{a}")
        for a in sorted(rj):
            lines.append(f"r\t{gid}\t{a}")
    fin = finals[str(F)]
    lines.append(f"#gfinal {F} {fin['streak']}")
    for gid, rank, score, nm, em in fin["ranks"]:
        lines.append(f"f\t{gid}\t{rank}\t{score}\t{nm}\t{em}")
    for gid, names in fin["eligible"].items():
        for n in names:
            lines.append(f"e\t{gid}\t{n}")
    return lines


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
    latest = {}   # 名前 → 最新の登録のギルドの値
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
                latest.pop(name, None)
                removed += 1
                break
            t = row_time(row[0])
            # 古いワールドのままの人は、この欄に最高ステージ（120 まで）を入れて送ってくる。討伐数としては数えない
            if t is None or t < KILLS_SINCE or rec["kills"] <= 120:
                rec["kills"] = 0
            latest[name] = rec.pop("guild", None)
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
    state = load_state()
    old_state = json.dumps(state, ensure_ascii=False, sort_keys=True)
    lines += guild_lines(latest, state)
    new_state = json.dumps(state, ensure_ascii=False, sort_keys=True)
    if new_state != old_state:
        os.makedirs(os.path.dirname(STATE), exist_ok=True)
        with open(STATE, "w", encoding="utf-8", newline="\n") as fp:
            json.dump(state, fp, ensure_ascii=False, sort_keys=True, indent=1)
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
