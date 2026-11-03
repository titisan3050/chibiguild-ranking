# ちびギルド放置録 ワールド全体ランキング

ワールドの「ランキング登録」で出る登録コードを Google フォームで集め、1 時間ごとに集計して
`docs/ranking.txt` を GitHub Pages で公開します。ワールドは
`https://titisan3050.github.io/chibiguild-ranking/ranking.txt` を読み込んで表示します。
すべて無料の範囲で動きます。

## 1. GitHub（このフォルダを公開する）

1. GitHub に `chibiguild-ranking` という名前の **Public** リポジトリを作り、このフォルダの中身を置く。
2. リポジトリの **Settings → Pages** で
   - Source: `Deploy from a branch`
   - Branch: `main`、フォルダ: `/docs`
   を選んで保存する。数分で `https://titisan3050.github.io/chibiguild-ranking/ranking.txt` が開けるようになる。

## 2. Google フォーム（登録の受付）

1. Google フォームで新しいフォームを作る。
   - 質問は 1 つ：「登録コード」（記述式・必須）
   - 設定 → 回答 → **メールアドレスを収集しない**（回答は公開されるため）
2. 「回答」タブ → **スプレッドシートにリンク** → 新しいスプレッドシートを作る。
3. スプレッドシートで **ファイル → 共有 → ウェブに公開**
   - 「フォームの回答 1」シート、形式 **カンマ区切り形式（.csv）** を選んで公開
   - 出てきた URL（`…/pub?gid=…&single=true&output=csv`）をコピーする
4. フォームの「送信」→ リンク → **URL を短縮** にチェックして、`https://forms.gle/…` をコピーする。

> ウェブに公開した CSV は誰でも見られます。中身は登録コード（名前と記録）と送信時刻だけです。

## 3. GitHub に URL を登録して動かす

1. リポジトリの **Settings → Secrets and variables → Actions → Variables** で、次の 2 つを追加する。
   - `SHEET_CSV_URL`：手順 2-3 の CSV の URL
   - `FORM_URL`：手順 2-4 の `https://forms.gle/…`
2. **Actions** タブ → `ranking` → **Run workflow** で 1 回動かす。以後は毎時自動で更新される。
   - 初回に Actions を有効にするか聞かれたら有効にする。

## しくみ

- 登録コード：`IGR1` + 本文 + `-` + 検査 6 桁。本文は 版・名前（文字コード 16 進）・攻撃力の桁（log10×1000）・
  最高ステージ・塔・転生・竜討伐・竜の格・その討伐数。検査の計算はワールド（`IGGame.RankCheck`）と `build_ranking.py` で同じ。
- 同じ名前で何回送っても、項目ごとに最高の値だけが残る。
- 検査が合わないコードと、ありえない値（ステージ 121 以上など）は数えない。
- 手元で試す：`python build_ranking.py 回答.csv`
