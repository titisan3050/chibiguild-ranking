// ちびギルド放置録：ランキング登録の中継（Cloudflare Workers）
//   VRChat のワールドは、Apps Script の受け口が返す転送（302 → googleusercontent.com）を
//   たどれず「Redirect limit exceeded」で失敗することがある。
//   この中継が受け口を読みにいき（転送は中でたどる）、返事の文字だけを 200 でそのまま返す。
//   記録は何も持たない。受け取るのは ?s=組&v=値 だけ（それ以外は受け口へ渡さない）
const GAS = "https://script.google.com/macros/s/AKfycbz0nehg1RibLOQFMvHMHYBw-pp6jggdRVyov4pHIG_j6HTbqIujce-2i2lxHJ9GBDkGFw/exec";

export default {
  async fetch(request) {
    const url = new URL(request.url);
    const s = url.searchParams.get("s");
    const v = url.searchParams.get("v");
    if (!/^\d{1,2}$/.test(s || "") || !/^\d{1,3}$/.test(v || "")) {
      return new Response("bad", { status: 400, headers: { "content-type": "text/plain; charset=utf-8" } });
    }
    let text = "error";
    try {
      const r = await fetch(`${GAS}?s=${s}&v=${v}`, { redirect: "follow" });
      text = (await r.text()).trim().slice(0, 64);
    } catch (e) {
      text = "error";
    }
    return new Response(text, { headers: { "content-type": "text/plain; charset=utf-8", "cache-control": "no-store" } });
  },
};
