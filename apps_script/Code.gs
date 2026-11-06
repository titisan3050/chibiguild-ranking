// ちびギルド放置録：ランキングの自動登録の受け口（Google Apps Script のウェブアプリ）
//   ワールドは記録を 1 バイトずつ、URL の ?s=組&v=値 の形で順に読みにくる（VRChat は読み込みしかできないため）。
//   v=256 で開始、0〜255 がデータ、257 で終わり。終わりで検査が合えば登録コードに直し、「auto」シートに 1 人 1 行で保存する。
//   ?csv=1 で auto シートを CSV で返す（GitHub の集計が読む）。
//
//   データの形：種類(1 登録・2 削除・3 登録＋ギルド) / 名前の文字数 / 名前（0〜127 はそのまま、ほかは 255,上位,下位）/
//              登録なら 7 つの数（7 ビットずつの可変長）/
//              種類 3 ならギルドの 10 の数（ID・合言葉の検査値・役職・版・紋章・今週の番号・今週の貢献・先週の番号・先週の貢献・通算）
//              ＋ギルド名（文字数と文字。マスターだけ送る）
//              ＋加入申請への判断の数と、判断ごとに（1 承認・2 見送り）と相手の名前の検査値 / 検査 2 バイト
//              役職 0 は「そのギルドへ加入を申請中」

const SHEET_NAME = 'auto';
const GROUPS = 16;

function rankCheck_(body) {
  let h = 7;
  const s = 'chibiguild' + body;
  for (let i = 0; i < s.length; i++) h = (h * 131 + s.charCodeAt(i) + 17) % 1000003;
  return h;
}

function hex4_(c) { return ('000' + c.toString(16)).slice(-4); }

function out_(t) { return ContentService.createTextOutput(t).setMimeType(ContentService.MimeType.TEXT); }

function doGet(e) {
  const p = (e && e.parameter) || {};
  if (p.csv) return csv_();
  const s = parseInt(p.s, 10), v = parseInt(p.v, 10);
  if (!(s >= 0 && s < GROUPS && v >= 0 && v <= 257)) return out_('bad');
  const lock = LockService.getScriptLock();
  lock.waitLock(10000);
  try {
    const cache = CacheService.getScriptCache();
    const key = 'b' + s;
    if (v === 256) { cache.put(key, '', 21600); return out_('start'); }
    let cur = cache.get(key);
    if (cur === null) return out_('nostart');
    if (v < 256) {
      cur = cur.length ? cur + ',' + v : String(v);
      if (cur.length > 3000) { cache.remove(key); return out_('long'); }
      cache.put(key, cur, 21600);
      return out_('ok');
    }
    cache.remove(key);
    const bytes = cur.length ? cur.split(',').map(Number) : [];
    const r = decode_(bytes);
    if (!r) return out_('bad');
    upsert_(r.name, r.code);
    return out_('saved');
  } finally {
    lock.releaseLock();
  }
}

function decode_(b) {
  if (b.length < 5) return null;
  const n = b.length - 2;
  let h = 7;
  for (let i = 0; i < n; i++) h = (h * 131 + b[i] + 17) % 65521;
  if (((h >> 8) & 255) !== b[n] || (h & 255) !== b[n + 1]) return null;
  let i = 0;
  const type = b[i++];
  const len = b[i++];
  if (len < 1 || len > 32) return null;
  let name = '';
  for (let k = 0; k < len; k++) {
    if (i >= n) return null;
    let c = b[i++];
    if (c === 255) {
      if (i + 1 >= n + 1) return null;
      c = b[i] * 256 + b[i + 1];
      i += 2;
    }
    name += String.fromCharCode(c);
  }
  function varint() {
    let x = 0, mul = 1, bt;
    do {
      if (i >= n) return null;
      bt = b[i++];
      x += (bt & 127) * mul;
      mul *= 128;
    } while (bt & 128);
    return x;
  }
  let hx = '';
  for (let k = 0; k < name.length; k++) hx += hex4_(name.charCodeAt(k));
  let body;
  if (type === 2) {
    if (i !== n) return null;
    body = '0.' + hx;
  } else if (type === 1 || type === 3) {
    const vals = [];
    for (let k = 0; k < 7; k++) {
      const x = varint();
      if (x === null) return null;
      vals.push(x);
    }
    if (type === 1) {
      if (i !== n) return null;
      body = '1.' + hx + '.' + vals.join('.');
    } else {
      const g = [];
      for (let k = 0; k < 10; k++) {
        const x = varint();
        if (x === null) return null;
        g.push(x);
      }
      if (i >= n) return null;
      const gl = b[i++];
      if (gl > 8) return null;
      let gh = '';
      for (let k = 0; k < gl; k++) {
        if (i >= n) return null;
        let c = b[i++];
        if (c === 255) {
          if (i + 1 >= n) return null;
          c = b[i] * 256 + b[i + 1];
          i += 2;
        }
        gh += hex4_(c);
      }
      let dh = '';
      if (i < n) {
        const dn = b[i++];
        if (dn > 8) return null;
        for (let k = 0; k < dn; k++) {
          const fl = varint(), hh = varint();
          if (fl === null || hh === null || fl < 1 || fl > 2 || hh > 0xffffff) return null;
          dh += fl.toString(16) + ('000000' + hh.toString(16)).slice(-6);
        }
      }
      if (i !== n) return null;
      body = '3.' + hx + '.' + vals.join('.') + '.' + g.join('.') + '.' + gh + '.' + dh;
    }
  } else return null;
  const ck = ('00000' + rankCheck_(body)).slice(-6);
  return { name: name, code: 'IGR1' + body + '-' + ck };
}

function sheet_() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  let sh = ss.getSheetByName(SHEET_NAME);
  if (!sh) {
    sh = ss.insertSheet(SHEET_NAME);
    sh.appendRow(['time', 'name', 'code']);
  }
  return sh;
}

function upsert_(name, code) {
  PropertiesService.getScriptProperties().setProperty('DIRTY', '1');   // 新しい登録があった → 次の kickGithub で集計を動かす
  const sh = sheet_();
  const vals = sh.getDataRange().getValues();
  const now = new Date().toISOString();
  for (let r = 1; r < vals.length; r++) {
    if (String(vals[r][1]) === name) {
      sh.getRange(r + 1, 1, 1, 3).setValues([[now, name, code]]);
      return;
    }
  }
  sh.appendRow([now, name, code]);
}

function csv_() {
  const vals = sheet_().getDataRange().getValues();
  const q = (x) => '"' + String(x).replace(/"/g, '""') + '"';
  const lines = [];
  for (let r = 1; r < vals.length; r++) lines.push(q(vals[r][0] instanceof Date ? vals[r][0].toISOString() : vals[r][0]) + ',' + q(vals[r][2]));
  return out_('time,code\n' + lines.join('\n'));
}

// ---- GitHub の集計を動かす（GitHub の定期実行は遅れたり止まったりするため、こちらから 5 分ごとに頼む）----
// 準備：プロジェクトの設定 → スクリプト プロパティに GH_TOKEN（chibiguild-ranking の Actions を読み書きできるトークン）を入れ、
//       エディタで installTrigger を 1 回実行する。新しい登録があったときだけ GitHub に頼む
function kickGithub() {
  const props = PropertiesService.getScriptProperties();
  const token = props.getProperty('GH_TOKEN');
  if (!token) return;
  const daily = new Date().getUTCHours() === 0 && new Date().getUTCMinutes() < 5;   // 1 日 1 回は変わりがなくても動かす
  if (props.getProperty('DIRTY') !== '1' && !daily) return;
  const res = UrlFetchApp.fetch('https://api.github.com/repos/titisan3050/chibiguild-ranking/actions/workflows/ranking.yml/dispatches', {
    method: 'post',
    contentType: 'application/json',
    headers: { Authorization: 'Bearer ' + token, Accept: 'application/vnd.github+json' },
    payload: JSON.stringify({ ref: 'main' }),
    muteHttpExceptions: true
  });
  if (res.getResponseCode() === 204) props.setProperty('DIRTY', '0');
  else Logger.log('GitHub: ' + res.getResponseCode() + ' ' + res.getContentText());
}

function installTrigger() {
  ScriptApp.getProjectTriggers().forEach(function (t) { if (t.getHandlerFunction() === 'kickGithub') ScriptApp.deleteTrigger(t); });
  ScriptApp.newTrigger('kickGithub').timeBased().everyMinutes(5).create();
  PropertiesService.getScriptProperties().setProperty('DIRTY', '1');
  kickGithub();
}

// 手元の確認用：エディタで実行すると、テストの登録 → 削除が auto シートに入る
function selfTest() {
  const name = 'TEST';
  const b = [1, name.length];
  for (let k = 0; k < name.length; k++) b.push(name.charCodeAt(k));
  [30000, 50, 10, 3, 2, 1, 1].forEach(function (x) { do { let t = x % 128; x = Math.floor(x / 128); b.push(x > 0 ? t | 128 : t); } while (x > 0); });
  let h = 7;
  for (let i = 0; i < b.length; i++) h = (h * 131 + b[i] + 17) % 65521;
  b.push((h >> 8) & 255, h & 255);
  Logger.log(JSON.stringify(decode_(b)));
}
