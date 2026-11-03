# ちびギルド放置録 ワールド全体ランキング

ワールドが自動で送ってくる記録を Google Apps Script の受け口で受け取り、5 分ごとに集計して
`docs/ranking.txt` を GitHub Pages で公開します。ワールドは
`https://titisan3050.github.io/chibiguild-ranking/ranking.txt` を 1 分ごとに読み込んで表示します。
すべて無料の範囲で動きます。

- 自動で届くのは、VRChat の設定で「信頼されていないURLを許可」を ON にしている人だけ
  （ワールドは読み込みしかできないので、受け口の URL を 1 バイトずつ読みにくる形で送る。1 回およそ 2〜3 分）。
- 板の「あなたの掲載」を OFF にすると、削除の合図を自動で送る。

## 受け口（Google Apps Script）

1. Google スプレッドシートを開き、**拡張機能 → Apps Script** を開く。
2. `コード.gs` の中身を、このフォルダの `apps_script/Code.gs` に置き換えて保存する。
3. **デプロイ → 新しいデプロイ → ウェブアプリ**（実行：自分／アクセス：全員）でデプロイし、URL（…/exec）をコピーする。
4. GitHub の **Settings → Secrets and variables → Actions → Variables** に `AUTO_URL` として登録する。
   ワールド（`IGBuilder.cs` の `RANK_AUTO_URL`）にも同じ URL を入れる。

- 受け口は同じスプレッドシートに `auto` シートを作り、1 人 1 行（最新の登録コード）で上書きする。`…/exec?csv=1` で CSV を返す。
- スクリプトを直したときは **デプロイ → デプロイを管理 → 編集 → 新バージョン** で更新する（URL は変わらない）。

## GitHub

- Pages：`main` ブランチの `/docs`。
- Actions：`ranking` が 5 分ごとに集計し、中身が変わったときだけ保存する（手で動かすときは Run workflow）。

## しくみ

- 登録コード：`IGR1` + 本文 + `-` + 検査 6 桁。本文は 版・名前（文字コード 16 進）・攻撃力の桁（log10×1000）・
  最高ステージ・塔・転生・竜討伐・竜の格・その討伐数。検査の計算はワールド（`IGGame.RankCheck`）・`Code.gs`・`build_ranking.py` で同じ。
- 削除コード（本文 = `0.` + 名前）が届くと、その人の記録を消す。あとで登録し直せばまた載る。
- 項目ごとに最高の値だけが残る。検査が合わないコードと、ありえない値は数えない。
- 手元で試す：`python build_ranking.py 自動登録.csv`
