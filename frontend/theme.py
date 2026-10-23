"""视觉系统：一套偏「旅行杂志 / 纸质行程单」的样式，避免通用的 AI 产品脸。

设计约束：
- 暖纸色底 + 墨绿黑字 + 陶土红强调色，不用紫蓝渐变。
- 标题用衬线体，正文用系统无衬线，元信息用等宽体。
- 分隔靠 1px 细线和留白，不堆阴影和圆角。
"""

from __future__ import annotations

import html
from typing import Any

from nicegui import ui

CSS = r"""
:root{
  --paper:#F4EFE3;
  --paper-deep:#EDE5D4;
  --surface:#FAF7EF;
  --card:#FFFDF7;
  --ink:#20241E;
  --ink-2:#454A40;
  --muted:#847F6E;
  --faint:#A9A292;
  --line:#DCD2BE;
  --line-2:#C7BCA0;
  --accent:#AE4A27;
  --accent-deep:#8A3417;
  --accent-wash:#F1E0D2;
  --pine:#2B5647;
  --pine-wash:#E2EAE3;
  --amber:#A1752A;
  --amber-wash:#F6EBD2;
  --danger:#A03A2A;
  --danger-wash:#F7E4DF;
  --ok:#3D6448;
  --serif:"Iowan Old Style","Palatino Linotype",Palatino,Georgia,"Songti SC","STSong","Source Han Serif SC","Noto Serif CJK SC","SimSun",serif;
  --sans:"Inter","Segoe UI","PingFang SC","Hiragino Sans GB","Microsoft YaHei","Noto Sans SC",sans-serif;
  --mono:"SFMono-Regular",Consolas,"Liberation Mono","Courier New",monospace;
}
*{box-sizing:border-box;}
html,body{height:100%;margin:0;background:var(--paper);color:var(--ink);font-family:var(--sans);}
body{-webkit-font-smoothing:antialiased;text-rendering:optimizeLegibility;}
body::after{
  content:"";position:fixed;inset:0;z-index:9998;pointer-events:none;opacity:.030;
  background-image:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='180' height='180'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.8' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='180' height='180' filter='url(%23n)' opacity='0.35'/%3E%3C/svg%3E");
}
::selection{background:var(--accent);color:#FFF9EF;}
*::-webkit-scrollbar{width:9px;height:9px;}
*::-webkit-scrollbar-track{background:transparent;}
*::-webkit-scrollbar-thumb{background:#CFC4AE;border:3px solid transparent;background-clip:content-box;border-radius:8px;}
*::-webkit-scrollbar-thumb:hover{background:#B6A98F;border:2px solid transparent;background-clip:content-box;}
button{font-family:inherit;}
a{color:var(--accent);text-decoration:none;}
:focus-visible{outline:2px solid var(--accent);outline-offset:2px;}

/* NiceGUI / Quasar 基线重置 */
.q-layout,.q-page-container,.q-page{background:var(--surface)!important;}
.q-page-container{height:100vh;}
.q-page{height:100vh;min-height:0!important;padding:0!important;}
.nicegui-content{padding:0!important;gap:0!important;display:block!important;height:100%;}
.q-btn{font-family:var(--sans);text-transform:none;letter-spacing:0;box-shadow:none!important;}
.q-field{font-family:var(--sans);}
.q-field__native,.q-field__input{color:var(--ink)!important;}
.q-field__label{color:var(--muted)!important;font-size:12px!important;}
.q-menu{background:var(--card)!important;border:1px solid var(--line-2);border-radius:3px!important;box-shadow:0 18px 48px -28px rgba(32,36,30,.55)!important;padding:4px!important;}
.q-item{color:var(--ink);font-size:12.5px;min-height:34px!important;border-radius:2px;padding:4px 10px!important;}
.q-item__section--side{color:var(--muted);min-width:22px!important;padding-right:6px!important;}
.q-item:hover,.q-item.q-manual-focusable--focused{background:var(--paper)!important;}
.q-notification{background:var(--ink)!important;color:#F8F2E4!important;border-radius:3px!important;font-size:12.5px!important;font-family:var(--sans)!important;box-shadow:0 18px 40px -22px rgba(0,0,0,.45)!important;padding:10px 14px!important;}
.q-notification.bg-negative{background:var(--danger)!important;}
.q-notification.bg-positive{background:var(--pine)!important;}
.q-notification.bg-warning{background:var(--amber)!important;color:#FFF8EA!important;}
.q-dialog__backdrop{background:rgba(28,32,26,.46)!important;backdrop-filter:blur(3px);}
.q-dialog__inner>.q-card{background:var(--card)!important;border:1px solid var(--line-2);border-radius:4px!important;box-shadow:0 40px 90px -50px rgba(20,24,18,.7)!important;color:var(--ink)!important;}
.q-tooltip{background:var(--ink)!important;color:#F8F2E4!important;font-size:11px!important;border-radius:2px!important;padding:5px 9px!important;font-family:var(--sans)!important;}
.q-linear-progress{color:var(--accent)!important;border-radius:0!important;}
.q-spinner{color:var(--accent)!important;}
.q-markdown img{max-width:100%;}
.q-markdown>:first-child{margin-top:0!important;}
.q-markdown>:last-child{margin-bottom:0!important;}

/* ---------- 外壳 ---------- */
.tpa-shell{display:flex;height:100%;min-height:100vh;background:var(--surface);overflow:hidden;}
.tpa-sidebar{
  width:292px;flex:0 0 292px;height:100%;display:flex;flex-direction:column;
  background:var(--paper-deep);border-right:1px solid var(--line);
  padding:22px 16px 14px;position:relative;z-index:40;
}
.tpa-main{flex:1;min-width:0;height:100%;display:flex;flex-direction:column;background:var(--surface);position:relative;}

.tpa-brand{display:flex;align-items:center;gap:11px;padding:2px 6px 0;margin-bottom:22px;flex:0 0 auto;}
.tpa-brand-mark{width:34px;height:34px;flex:0 0 34px;color:var(--accent);}
.tpa-brand-text{display:flex;flex-direction:column;gap:1px;min-width:0;}
.tpa-brand-name{font-family:var(--serif);font-size:20px;line-height:1.1;letter-spacing:.14em;color:var(--ink);font-weight:600;}
.tpa-brand-sub{font-family:var(--mono);font-size:8.5px;letter-spacing:.22em;color:var(--muted);text-transform:uppercase;}

.tpa-newbtn{
  width:100%;height:42px;flex:0 0 auto;background:var(--ink);color:#FAF5E8;border:1px solid var(--ink);
  border-radius:2px;display:flex;align-items:center;justify-content:space-between;
  padding:0 13px;font-size:13px;letter-spacing:.04em;transition:background .18s ease,border-color .18s ease;
}
.tpa-newbtn:hover{background:var(--accent);border-color:var(--accent);color:#FFF9EE;}
.tpa-newbtn .q-btn__content{width:100%;justify-content:space-between;flex-wrap:nowrap;}
.tpa-newbtn .tpa-newbtn-left{display:flex;align-items:center;gap:9px;}

.side-scroll{flex:1;min-height:0;overflow-y:auto;overflow-x:hidden;margin:18px -4px 8px;padding:0 4px;}
.side-section{margin:0 0 20px;}
.side-label{
  display:flex;align-items:center;justify-content:space-between;
  font-family:var(--mono);font-size:9.5px;letter-spacing:.18em;text-transform:uppercase;
  color:var(--faint);padding:0 8px;margin-bottom:7px;
}
.side-label .count{letter-spacing:.02em;color:var(--muted);}
.side-group{font-size:9.5px;font-family:var(--mono);letter-spacing:.12em;color:var(--faint);padding:9px 8px 4px;text-transform:uppercase;}

.conv-item{
  display:flex;align-items:flex-start;gap:8px;width:100%;text-align:left;cursor:pointer;
  border:0;border-left:2px solid transparent;background:transparent;padding:9px 4px 9px 10px;
  border-radius:2px;transition:background .15s ease,border-color .15s ease;
}
.conv-item:hover{background:rgba(255,253,247,.66);}
.conv-item.active{background:var(--card);border-left-color:var(--accent);box-shadow:0 1px 0 rgba(32,36,30,.04);}
.conv-main{flex:1;min-width:0;display:flex;flex-direction:column;gap:3px;}
.conv-title{font-size:13px;line-height:1.35;font-weight:600;color:var(--ink);overflow:hidden;text-overflow:ellipsis;white-space:nowrap;}
.conv-meta{display:flex;align-items:center;gap:6px;font-family:var(--mono);font-size:10px;color:var(--muted);line-height:1.3;}
.conv-meta .trip-dot{width:4px;height:4px;border-radius:50%;background:var(--accent);display:inline-block;}
.conv-more{width:22px;height:22px;flex:0 0 22px;opacity:0;transition:opacity .15s ease;display:flex;align-items:center;justify-content:center;color:var(--muted);background:transparent;border:0;border-radius:2px;margin-top:-2px;cursor:pointer;}
.conv-item:hover .conv-more,.conv-item.active .conv-more{opacity:1;}
.conv-more:hover{background:var(--paper-deep);color:var(--ink);}
.conv-empty{font-size:11.5px;color:var(--muted);line-height:1.7;padding:8px 10px;}

.side-nav{display:flex;flex-direction:column;gap:2px;}
.side-nav-item{
  display:flex;align-items:center;gap:10px;width:100%;text-align:left;background:transparent;border:0;
  padding:9px 10px;border-radius:2px;color:var(--ink-2);font-size:12.5px;cursor:pointer;
  border-left:2px solid transparent;transition:background .15s ease,color .15s ease;
}
.side-nav-item:hover{background:rgba(255,253,247,.66);color:var(--ink);}
.side-nav-item.active{background:var(--card);border-left-color:var(--accent);color:var(--ink);font-weight:600;}
.side-nav-icon{width:17px;height:17px;color:var(--muted);display:flex;align-items:center;}
.side-nav-item.active .side-nav-icon{color:var(--accent);}
.side-nav-sub{margin-left:auto;font-family:var(--mono);font-size:9.5px;color:var(--faint);}

.side-user{flex:0 0 auto;border-top:1px solid var(--line);padding:12px 6px 2px;display:flex;align-items:center;gap:9px;}
.side-user-id{display:flex;align-items:center;gap:9px;flex:1;min-width:0;border:0;background:transparent;padding:0;cursor:pointer;text-align:left;}
.side-user-id:hover .side-user-name{color:var(--accent);}
.avatar{
  width:29px;height:29px;flex:0 0 29px;border-radius:50%;background:var(--pine);color:#F4EFE3;
  display:flex;align-items:center;justify-content:center;font-family:var(--serif);font-size:13px;
  text-transform:uppercase;letter-spacing:.02em;
}
.side-user-info{flex:1;min-width:0;display:flex;flex-direction:column;line-height:1.3;}
.side-user-name{font-size:12.5px;font-weight:600;color:var(--ink);overflow:hidden;text-overflow:ellipsis;white-space:nowrap;}
.side-user-role{font-family:var(--mono);font-size:9px;letter-spacing:.12em;color:var(--muted);text-transform:uppercase;}
.side-user-btn{width:26px;height:26px;border:0;background:transparent;color:var(--muted);display:flex;align-items:center;justify-content:center;border-radius:2px;cursor:pointer;}
.side-user-btn:hover{background:var(--card);color:var(--ink);}

/* ---------- 顶栏 ---------- */
.tpa-topbar{
  flex:0 0 64px;height:64px;display:flex;align-items:center;gap:14px;padding:0 28px;
  border-bottom:1px solid var(--line);background:rgba(250,247,239,.94);position:relative;z-index:20;
}
.topbar-left{flex:1;min-width:0;display:flex;align-items:center;gap:12px;}
.topbar-text{min-width:0;display:flex;flex-direction:column;gap:2px;}
.topbar-title{font-family:var(--serif);font-size:17px;line-height:1.2;color:var(--ink);letter-spacing:.01em;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}
.topbar-sub{font-family:var(--mono);font-size:9.5px;letter-spacing:.12em;color:var(--muted);text-transform:uppercase;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}
.topbar-right{display:flex;align-items:center;gap:6px;flex:0 0 auto;}
.topbar-divider{width:1px;height:18px;background:var(--line);margin:0 6px;}
.tpa-menu-btn{display:none!important;}

.iconbtn{
  width:30px;height:30px;border:1px solid transparent;background:transparent;color:var(--muted);
  display:inline-flex;align-items:center;justify-content:center;border-radius:2px;cursor:pointer;
  transition:color .15s ease,background .15s ease,border-color .15s ease;padding:0;
}
.iconbtn:hover{background:var(--card);border-color:var(--line);color:var(--ink);}
.iconbtn:disabled{opacity:.35;cursor:not-allowed;}
.iconbtn.dark{color:var(--ink-2);}
.iconbtn.mini{width:26px;height:26px;}

.conn{display:inline-flex;align-items:center;gap:6px;font-family:var(--mono);font-size:9.5px;letter-spacing:.1em;color:var(--muted);text-transform:uppercase;}
.conn-dot{width:6px;height:6px;border-radius:50%;background:var(--ok);box-shadow:0 0 0 3px rgba(61,100,72,.1);}
.conn-dot.warn{background:var(--amber);box-shadow:0 0 0 3px rgba(161,117,42,.12);}
.conn-dot.off{background:var(--danger);box-shadow:0 0 0 3px rgba(160,58,42,.12);}

/* ---------- 横幅 / 状态条 ---------- */
.tpa-banner{
  flex:0 0 auto;display:flex;align-items:center;gap:9px;padding:8px 28px;
  background:var(--amber-wash);border-bottom:1px solid #E4D2AA;color:#6D4E16;font-size:12px;line-height:1.5;
}
.tpa-banner.danger{background:var(--danger-wash);border-bottom-color:#E6C4BA;color:#7C2B1E;}
.tpa-banner .icon{flex:0 0 auto;display:flex;}
.tpa-banner .spacer{flex:1;}

.tpa-thinking{
  flex:0 0 auto;height:30px;display:flex;align-items:center;gap:8px;padding:0 28px;position:relative;
  background:var(--paper);border-bottom:1px solid var(--line);color:var(--ink-2);
  font-family:var(--mono);font-size:10.5px;letter-spacing:.04em;overflow:hidden;
  transition:height .22s ease,opacity .22s ease,padding .22s ease;
}
.tpa-thinking.hidden{height:0;opacity:0;border-bottom-color:transparent;padding-top:0;padding-bottom:0;}
.tpa-thinking .dot{width:5px;height:5px;border-radius:50%;background:var(--accent);animation:tpaPulse 1.15s ease-in-out infinite;}
.tpa-thinking .track{position:absolute;left:0;bottom:-1px;height:1px;width:100%;background:linear-gradient(90deg,transparent,var(--accent),transparent);background-size:220% 100%;animation:tpaSlide 1.9s linear infinite;}
@keyframes tpaPulse{0%,100%{opacity:.25;transform:scale(.85);}50%{opacity:1;transform:scale(1);}}
@keyframes tpaSlide{0%{background-position:120% 0;}100%{background-position:-120% 0;}}

/* ---------- 聊天滚动区 ---------- */
.tpa-chat-scroll{flex:1;min-height:0;overflow-y:auto;overflow-x:hidden;scroll-behavior:auto;position:relative;}
.tpa-chat-inner{max-width:820px;margin:0 auto;padding:36px 34px 26px;}
.tpa-chat-inner.is-empty{min-height:100%;display:flex;flex-direction:column;justify-content:center;}
.tpa-chat-inner.is-empty .tpa-hero{padding:10px 0 28px;}
.tpa-chat-empty{align-items:center;}

/* ---------- 空态 ---------- */
.tpa-hero{max-width:700px;margin:0 auto;padding:7vh 0 30px;}
.tpa-kicker{display:flex;align-items:center;gap:10px;font-family:var(--mono);font-size:9.5px;letter-spacing:.24em;text-transform:uppercase;color:var(--accent);}
.tpa-kicker::before{content:"";width:24px;height:1px;background:var(--accent);}
.tpa-hero h1{font-family:var(--serif);font-size:clamp(34px,4.2vw,50px);font-weight:500;line-height:1.18;letter-spacing:-.01em;margin:16px 0 13px;color:var(--ink);}
.tpa-hero h1 em{font-style:normal;color:var(--accent);}
.tpa-hero p{margin:0;font-size:13.5px;line-height:1.85;color:var(--muted);max-width:56ch;}
.prompt-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:11px;margin-top:32px;}
.prompt-card{
  text-align:left;border:1px solid var(--line);background:var(--card);padding:14px 14px 12px;border-radius:2px;
  display:flex;flex-direction:column;gap:11px;min-height:124px;cursor:pointer;
  transition:transform .18s ease,border-color .18s ease,box-shadow .18s ease;
}
.prompt-card:hover{border-color:var(--ink);transform:translateY(-2px);box-shadow:0 14px 26px -24px rgba(32,36,30,.7);}
.prompt-card:active{transform:translateY(0);}
.prompt-top{display:flex;align-items:center;justify-content:space-between;}
.prompt-index{font-family:var(--mono);font-size:9.5px;letter-spacing:.14em;color:var(--faint);}
.prompt-arrow{color:var(--faint);display:flex;transition:transform .18s ease,color .18s ease;}
.prompt-card:hover .prompt-arrow{color:var(--accent);transform:translateX(2px);}
.prompt-text{font-size:12.8px;line-height:1.65;color:var(--ink-2);flex:1;}
.hero-note{margin-top:24px;display:flex;align-items:center;gap:8px;font-family:var(--mono);font-size:9.5px;letter-spacing:.1em;text-transform:uppercase;color:var(--faint);}
.hero-note::before{content:"";width:16px;height:1px;background:var(--line-2);}

/* ---------- 输入区 ---------- */
.tpa-composer-wrap{flex:0 0 auto;padding:10px 34px 20px;background:linear-gradient(to top,var(--surface) 62%,rgba(250,247,239,0));}
.tpa-composer{
  max-width:820px;margin:0 auto;background:var(--card);border:1px solid var(--line-2);border-radius:3px;
  padding:13px 12px 9px 16px;box-shadow:0 20px 44px -42px rgba(32,36,30,.9);
  transition:border-color .18s ease,box-shadow .18s ease;
}
.tpa-composer:focus-within{border-color:var(--ink);box-shadow:0 0 0 1px var(--ink),0 20px 44px -42px rgba(32,36,30,.9);}
.tpa-composer.is-disabled{background:var(--paper);border-color:var(--line);}
.composer-row{display:flex;align-items:flex-end;gap:10px;}
.composer-field{flex:1;min-width:0;}
.composer-field .q-field__control{background:transparent!important;padding:0!important;min-height:38px!important;}
.composer-field .q-field__control:before,.composer-field .q-field__control:after{display:none!important;}
.composer-field .q-field__native{font-size:14.5px!important;line-height:1.75!important;padding:5px 0!important;color:var(--ink)!important;resize:none;}
.composer-field textarea{max-height:190px;overflow-y:auto!important;}
.composer-field .q-field__native::placeholder{color:var(--faint)!important;}
.composer-hint{display:flex;align-items:center;gap:12px;padding:7px 2px 0;font-family:var(--mono);font-size:9.5px;letter-spacing:.06em;color:var(--faint);}
.composer-hint .spacer{flex:1;}
.composer-count{color:var(--muted);}
.composer-count.over{color:var(--danger);}
.tpa-send{
  width:36px;height:36px;min-height:36px;flex:0 0 36px;border-radius:2px;background:var(--accent);color:#FFF8ED;
  display:flex;align-items:center;justify-content:center;border:1px solid var(--accent);cursor:pointer;
  transition:background .16s ease,color .16s ease,border-color .16s ease;
}
.tpa-send:hover{background:var(--accent-deep);border-color:var(--accent-deep);}
.tpa-send.stop{background:var(--ink);border-color:var(--ink);}
.tpa-send.stop:hover{background:var(--accent);border-color:var(--accent);}
.tpa-send:disabled{background:var(--line);border-color:var(--line);color:var(--faint);cursor:not-allowed;}
.tpa-send .q-btn__content{width:100%;height:100%;}
.tpa-send .spinner-mini{width:15px;height:15px;border:1.5px solid rgba(255,248,237,.35);border-top-color:#FFF8ED;border-radius:50%;animation:tpaSpin .7s linear infinite;}
@keyframes tpaSpin{to{transform:rotate(360deg);}}

/* ---------- 消息 ---------- */
.msg{position:relative;margin:0 0 30px;animation:tpaRise .3s ease-out both;}
@keyframes tpaRise{from{opacity:0;transform:translateY(6px);}to{opacity:1;transform:none;}}
.msg-user{display:flex;justify-content:flex-end;}
.msg-user-box{
  max-width:78%;background:var(--paper-deep);border:1px solid var(--line);border-radius:3px 3px 0 3px;
  padding:11px 15px;font-size:14px;line-height:1.78;color:var(--ink);white-space:pre-wrap;word-break:break-word;
}
.msg-assistant{display:block;}
.msg-head{display:flex;align-items:center;gap:9px;margin-bottom:8px;min-height:22px;}
.msg-role{font-family:var(--mono);font-size:9.5px;letter-spacing:.15em;text-transform:uppercase;color:var(--muted);display:flex;align-items:center;gap:7px;}
.msg-role b{color:var(--pine);font-weight:600;letter-spacing:.12em;}
.msg-role .role-name{color:var(--pine);font-weight:600;letter-spacing:.12em;}
.msg-role .rule{width:14px;height:1px;background:var(--line-2);display:inline-block;}
.msg-time{font-family:var(--mono);font-size:9.5px;color:var(--faint);letter-spacing:.04em;}
.msg-actions{margin-left:auto;display:flex;align-items:center;gap:2px;opacity:0;transition:opacity .18s ease;}
.msg:hover .msg-actions,.msg:focus-within .msg-actions{opacity:1;}
.msg-actions .iconbtn{width:25px;height:25px;}
.tpa-md{font-size:14.5px;line-height:1.85;color:var(--ink-2);word-break:break-word;}
.msg-content>:first-child{margin-top:0!important;}
.msg-content>:last-child{margin-bottom:0!important;}
.msg-content>*+*{margin-top:10px;}
.json-block{border:1px solid var(--line);background:var(--paper);border-radius:2px;overflow:hidden;}
.json-summary{display:flex;align-items:center;gap:8px;padding:8px 11px;cursor:pointer;list-style:none;font-family:var(--mono);font-size:9.5px;letter-spacing:.08em;text-transform:uppercase;color:var(--muted);}
.json-summary::-webkit-details-marker{display:none;}
.json-summary:hover{background:var(--paper-deep);color:var(--ink-2);}
.json-summary .json-hint{margin-left:auto;color:var(--faint);letter-spacing:.02em;text-transform:none;}
.json-pre{margin:0;padding:10px 12px;border-top:1px solid var(--line);font-family:var(--mono);font-size:9.5px;line-height:1.7;color:var(--ink-2);white-space:pre;overflow:auto;max-height:300px;background:var(--card);}
.tpa-md p{margin:0 0 .82em;}
.tpa-md p:last-child{margin-bottom:0;}
.tpa-md strong{color:var(--ink);font-weight:650;}
.tpa-md h1,.tpa-md h2,.tpa-md h3,.tpa-md h4{font-family:var(--serif);color:var(--ink);line-height:1.35;margin:1.15em 0 .5em;font-weight:600;}
.tpa-md h1{font-size:1.45em;}
.tpa-md h2{font-size:1.26em;}
.tpa-md h3{font-size:1.1em;}
.tpa-md ul,.tpa-md ol{margin:.35em 0 .9em;padding-left:1.35em;}
.tpa-md li{margin:.22em 0;padding-left:.15em;}
.tpa-md li::marker{color:var(--accent);}
.tpa-md code{font-family:var(--mono);font-size:.86em;background:var(--paper-deep);border:1px solid var(--line);border-radius:2px;padding:1px 5px;color:var(--ink);}
.tpa-md pre{background:var(--paper-deep);border:1px solid var(--line);border-radius:2px;padding:12px 14px;overflow-x:auto;margin:.7em 0;}
.tpa-md pre code{background:transparent;border:0;padding:0;font-size:12.5px;line-height:1.7;}
.tpa-md blockquote{margin:.7em 0;padding:.1em 0 .1em 14px;border-left:2px solid var(--line-2);color:var(--muted);}
.tpa-md a{color:var(--accent);text-decoration:underline;text-underline-offset:3px;text-decoration-thickness:1px;}
.tpa-md table{border-collapse:collapse;width:100%;margin:.7em 0;font-size:13px;}
.tpa-md th{font-family:var(--mono);font-size:10px;letter-spacing:.08em;text-transform:uppercase;color:var(--muted);font-weight:500;text-align:left;border-bottom:1px solid var(--line-2);padding:7px 9px;}
.tpa-md td{border-bottom:1px solid var(--line);padding:7px 9px;color:var(--ink-2);}
.tpa-md hr{border:0;border-top:1px solid var(--line);margin:1.2em 0;}
.tpa-caret{display:inline-block;width:6px;height:1.02em;background:var(--accent);margin-left:3px;vertical-align:-2px;animation:tpaBlink 1s steps(1) infinite;}
@keyframes tpaBlink{50%{opacity:0;}}
.msg-fail{
  display:flex;align-items:center;gap:10px;margin-top:11px;padding:8px 12px;
  border:1px solid #E3C1B6;background:var(--danger-wash);border-radius:2px;color:#7C2B1E;font-size:12px;line-height:1.5;
}
.msg-fail .icon{display:flex;flex:0 0 auto;}
.msg-fail .spacer{flex:1;}
.msg-fail .retry{font-family:var(--mono);font-size:10px;letter-spacing:.06em;color:#7C2B1E;background:transparent;border:1px solid #D9AFA2;border-radius:2px;padding:3px 8px;cursor:pointer;}
.msg-fail .retry:hover{background:#F2D5CC;}
.msg-cancelled{display:inline-flex;align-items:center;gap:6px;margin-top:10px;font-size:11.5px;color:var(--muted);font-family:var(--mono);letter-spacing:.04em;}
.msg-cancelled .dash{width:12px;height:1px;background:var(--line-2);}
.msg-cancelled .dot-pending{width:5px;height:5px;border-radius:50%;background:var(--amber);animation:tpaPulse 1.2s ease-in-out infinite;}
.msg-meta{margin-top:12px;display:flex;align-items:center;gap:10px;}

/* ---------- 工具面板 ---------- */
.tools{border:1px solid var(--line);background:var(--card);border-radius:2px;margin:0 0 14px;overflow:hidden;max-width:640px;}
.tools-head{display:flex;align-items:center;gap:8px;padding:8px 11px;cursor:pointer;user-select:none;background:var(--paper);transition:background .15s ease;}
.tools-head:hover{background:var(--paper-deep);}
.tools-head .chev{display:flex;color:var(--muted);transition:transform .18s ease;}
.tools.open .tools-head .chev{transform:rotate(90deg);}
.tools-title{font-size:11.5px;color:var(--ink-2);letter-spacing:.02em;}
.tools-count{font-family:var(--mono);font-size:10px;color:var(--muted);letter-spacing:.03em;}
.tools-head .spacer{flex:1;}
.tools-dur{font-family:var(--mono);font-size:9.5px;color:var(--faint);}
.tools-body{display:none;border-top:1px solid var(--line);padding:3px 0;}
.tools.open .tools-body{display:block;}
.tool-row{display:grid;grid-template-columns:16px minmax(96px,1.2fr) .62fr 54px minmax(0,1.6fr);gap:9px;align-items:center;padding:6px 11px;border-bottom:1px solid rgba(220,210,190,.55);font-size:11px;min-height:29px;}
.tool-row:last-child{border-bottom:0;}
.tool-row.failed{background:rgba(160,58,42,.045);}
.tool-icon{display:flex;align-items:center;justify-content:center;color:var(--ok);}
.tool-row.failed .tool-icon{color:var(--danger);}
.tool-icon.pending{color:var(--amber);}
.tool-name{font-family:var(--mono);font-size:10.5px;color:var(--ink);overflow:hidden;text-overflow:ellipsis;white-space:nowrap;}
.tool-server{font-family:var(--mono);font-size:8.5px;letter-spacing:.1em;text-transform:uppercase;color:var(--faint);}
.tool-ms{font-family:var(--mono);font-size:9.5px;color:var(--muted);text-align:right;}
.tool-summary{font-size:11px;color:var(--ink-2);overflow:hidden;text-overflow:ellipsis;white-space:nowrap;}
.tool-more{grid-column:2 / -1;display:none;padding:2px 0 6px;}
.tool-row.expanded + .tool-more{display:block;}
.tool-args-label{font-family:var(--mono);font-size:8px;letter-spacing:.16em;color:var(--faint);margin-bottom:3px;}
.tool-args{font-family:var(--mono);font-size:9.5px;line-height:1.6;color:var(--muted);background:var(--paper);border:1px solid var(--line);padding:6px 8px;border-radius:2px;white-space:pre-wrap;word-break:break-all;margin:0;}
.tools-note{font-family:var(--mono);font-size:9px;color:var(--faint);padding:5px 11px 7px;letter-spacing:.02em;}

/* ---------- 引用 ---------- */
.cites{margin-top:16px;border-top:1px dashed var(--line);padding-top:10px;max-width:660px;}
.cites-head{display:flex;align-items:center;gap:7px;font-family:var(--mono);font-size:9.5px;letter-spacing:.1em;text-transform:uppercase;color:var(--faint);cursor:pointer;user-select:none;}
.cites-head:hover{color:var(--muted);}
.cites-body{display:none;margin-top:8px;flex-direction:column;gap:7px;}
.cites.open .cites-body{display:flex;}
.cite{display:flex;gap:9px;font-size:11.5px;line-height:1.65;color:var(--ink-2);}
.cite-num{font-family:var(--mono);font-size:9.5px;color:var(--accent);flex:0 0 14px;padding-top:1px;}
.cite-main{min-width:0;}
.cite-head{display:flex;align-items:baseline;gap:6px;flex-wrap:wrap;}
.cite-title{color:var(--ink);font-weight:600;}
.cite-score{font-family:var(--mono);font-size:9px;color:var(--faint);margin-left:6px;}
.cite-snippet{color:var(--muted);margin-top:1px;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;}

/* ---------- 行程卡片 ---------- */
.trip{
  margin:20px 0 10px;background:var(--card);border:1px solid var(--line-2);border-radius:2px;position:relative;
  box-shadow:0 24px 50px -46px rgba(32,36,30,.75);
}
.trip::before,.trip::after{content:"";position:absolute;width:9px;height:9px;pointer-events:none;}
.trip::before{top:-1px;left:-1px;border-top:2px solid var(--accent);border-left:2px solid var(--accent);}
.trip::after{bottom:-1px;right:-1px;border-bottom:2px solid var(--accent);border-right:2px solid var(--accent);}
.trip-head{padding:22px 24px 17px;border-bottom:1px solid var(--line);}
.trip-head-top{display:flex;align-items:flex-start;gap:16px;}
.trip-head-main{flex:1;min-width:0;}
.trip-kicker{font-family:var(--mono);font-size:9px;letter-spacing:.22em;text-transform:uppercase;color:var(--accent);margin-bottom:7px;display:flex;align-items:center;gap:8px;}
.trip-kicker::before{content:"";width:16px;height:1px;background:var(--accent);}
.trip-title{font-family:var(--serif);font-size:25px;line-height:1.25;letter-spacing:.005em;color:var(--ink);margin:0;font-weight:600;}
.trip-sub{display:flex;align-items:center;flex-wrap:wrap;gap:7px 13px;margin-top:9px;font-family:var(--mono);font-size:10px;letter-spacing:.04em;color:var(--muted);}
.trip-sub .sep{width:3px;height:3px;border-radius:50%;background:var(--line-2);}
.trip-export{
  flex:0 0 auto;display:inline-flex;align-items:center;gap:6px;height:30px;padding:0 10px;
  border:1px solid var(--line-2);background:transparent;color:var(--ink-2);font-size:11px;border-radius:2px;cursor:pointer;
  transition:border-color .15s ease,color .15s ease,background .15s ease;
}
.trip-export:hover{border-color:var(--ink);color:var(--ink);background:var(--paper);}
.trip-summary{margin:13px 0 0;font-size:12.5px;line-height:1.78;color:var(--ink-2);}
.trip-summary::before{content:"摘要";font-family:var(--mono);font-size:8.5px;letter-spacing:.16em;color:var(--faint);display:block;margin-bottom:3px;text-transform:uppercase;}

.budget{padding:16px 24px 17px;border-bottom:1px solid var(--line);}
.budget-top{display:flex;align-items:baseline;gap:10px;flex-wrap:wrap;}
.budget-label{font-family:var(--mono);font-size:8.5px;letter-spacing:.18em;text-transform:uppercase;color:var(--muted);}
.budget-total{font-family:var(--serif);font-size:27px;line-height:1;color:var(--ink);letter-spacing:.01em;}
.budget-total .cur{font-size:15px;color:var(--muted);margin-right:2px;}
.budget-note{margin-left:auto;font-family:var(--mono);font-size:9px;color:var(--faint);letter-spacing:.06em;}
.budget-bar{display:flex;gap:2px;height:9px;margin:12px 0 10px;background:var(--paper-deep);border-radius:1px;overflow:hidden;}
.budget-seg{height:100%;min-width:2px;transition:filter .15s ease;}
.budget-seg:hover{filter:brightness(1.12);}
.budget-legend{display:flex;flex-wrap:wrap;gap:5px 17px;}
.legend-item{display:inline-flex;align-items:center;gap:6px;font-size:10.5px;color:var(--ink-2);}
.legend-swatch{width:7px;height:7px;border-radius:1px;flex:0 0 7px;}
.legend-amount{font-family:var(--mono);font-size:9.5px;color:var(--muted);}

.day{border-bottom:1px solid var(--line);}
.day:last-of-type{border-bottom:0;}
.day-head{display:flex;align-items:center;gap:13px;padding:14px 24px;cursor:pointer;user-select:none;transition:background .15s ease;}
.day-head:hover{background:rgba(244,239,227,.5);}
.day-index{font-family:var(--serif);font-size:26px;line-height:1;color:var(--line-2);flex:0 0 auto;min-width:35px;letter-spacing:-.02em;}
.day.closed .day-index{color:var(--faint);}
.day-info{flex:1;min-width:0;display:flex;flex-direction:column;gap:3px;}
.day-line{display:flex;align-items:center;gap:8px;flex-wrap:wrap;}
.day-date{font-size:12.5px;font-weight:650;color:var(--ink);letter-spacing:.02em;}
.day-weekday{font-family:var(--mono);font-size:9.5px;color:var(--muted);letter-spacing:.04em;}
.day-theme{font-size:11.5px;color:var(--muted);overflow:hidden;text-overflow:ellipsis;white-space:nowrap;}
.day-weather{
  flex:0 0 auto;display:inline-flex;align-items:center;gap:5px;padding:3px 8px;border:1px solid var(--line);
  border-radius:99px;font-family:var(--mono);font-size:9.5px;color:var(--ink-2);background:var(--paper);
}
.day-weather .icon{display:flex;color:var(--amber);}
.day-chev{flex:0 0 auto;color:var(--muted);display:flex;transition:transform .18s ease;}
.day.closed .day-chev{transform:rotate(-90deg);}
.day-body{padding:2px 24px 14px;}
.day.closed .day-body{display:none;}

.stop{display:grid;grid-template-columns:88px 16px minmax(0,1fr);gap:0 13px;padding:11px 0 3px;position:relative;}
.stop-time{font-family:var(--mono);font-size:10.5px;line-height:1.6;color:var(--muted);text-align:right;padding-top:2px;white-space:nowrap;letter-spacing:.02em;}
.stop-time .end{color:var(--faint);}
.stop-spine{position:relative;display:flex;justify-content:center;}
.stop-spine::before{content:"";position:absolute;top:12px;bottom:-16px;width:1px;background:var(--line);}
.stop:last-child .stop-spine::before{display:none;}
.stop-dot{width:7px;height:7px;border-radius:50%;background:var(--card);border:1.5px solid var(--accent);margin-top:5px;position:relative;z-index:1;}
.stop.is-meal .stop-dot{border-color:var(--amber);}
.stop.is-transport .stop-dot{border-color:var(--muted);}
.stop-content{min-width:0;padding-bottom:10px;}
.stop-title{font-size:13.5px;font-weight:650;line-height:1.5;color:var(--ink);}
.stop-meta{display:flex;align-items:center;flex-wrap:wrap;gap:4px 9px;margin-top:3px;font-size:11px;line-height:1.6;color:var(--muted);}
.stop-meta .sep{width:2px;height:2px;border-radius:50%;background:var(--line-2);}
.stop-meta .pin{display:inline-flex;align-items:center;gap:4px;}
.stop-meta .pin .icon{display:flex;color:var(--faint);}
.stop-meta .free{color:var(--ok);}
.stop-transport{display:flex;align-items:center;gap:5px;margin-top:5px;font-family:var(--mono);font-size:9.5px;color:var(--faint);letter-spacing:.02em;}
.stop-transport .icon{display:flex;}
.stop-note{
  margin-top:7px;padding:6px 9px;background:var(--paper);border-left:2px solid var(--line-2);
  font-size:11px;line-height:1.7;color:var(--ink-2);
}
.stop-note .note-mark{color:var(--amber);margin-right:4px;font-family:var(--mono);font-size:8.5px;letter-spacing:.1em;}
.stop.model{
  margin-left:-11px;padding-left:10px;border-left:3px solid #B8B2A2;background:rgba(120,116,104,.045);
  position:relative;
}
.stop.model .stop-spine::before{background:#D4CEBE;}
.stop.model .stop-dot{border-color:#9C9686;}
.model-tag{
  position:absolute;top:9px;right:0;font-family:var(--mono);font-size:8px;letter-spacing:.12em;
  text-transform:uppercase;color:var(--muted);opacity:.6;padding:1px 4px;border:1px solid var(--line);border-radius:1px;
}
.free-day{display:flex;align-items:center;gap:8px;padding:12px 0 8px 117px;font-size:11.5px;color:var(--faint);font-style:italic;}

.trip-risks{padding:15px 24px 16px;background:linear-gradient(180deg,rgba(246,235,210,.35),rgba(246,235,210,.12));border-bottom:1px solid var(--line);}
.trip-risks-head{display:flex;align-items:center;gap:7px;font-family:var(--mono);font-size:9.5px;letter-spacing:.14em;text-transform:uppercase;color:#7C5A18;cursor:pointer;user-select:none;}
.trip-risks-head .icon{display:flex;color:var(--amber);}
.trip-risks-head .spacer{flex:1;}
.trip-risks-head .chev{display:flex;transition:transform .18s ease;}
.trip-risks.open .trip-risks-head .chev{transform:rotate(90deg);}
.trip-risks-body{display:none;flex-direction:column;gap:8px;margin-top:9px;}
.trip-risks.open .trip-risks-body{display:flex;}
.risk{display:grid;grid-template-columns:14px minmax(0,1fr);gap:8px;font-size:11.5px;line-height:1.7;color:var(--ink-2);}
.risk-num{font-family:var(--mono);font-size:9px;color:var(--faint);padding-top:2px;}
.risk-desc{color:var(--ink);}
.risk-arrow{color:var(--faint);margin:0 5px;font-family:var(--mono);}
.risk-fix{color:var(--muted);}
.trip-pack{padding:12px 24px;display:flex;align-items:flex-start;flex-wrap:wrap;gap:4px 8px;font-size:11.5px;line-height:1.7;color:var(--ink-2);}
.trip-pack .icon{display:flex;color:var(--pine);margin-top:2px;}
.trip-pack .packing-label{font-family:var(--mono);font-size:9px;letter-spacing:.12em;text-transform:uppercase;color:var(--muted);padding-top:3px;white-space:nowrap;}
.trip-pack .packing-items{font-size:11.5px;line-height:1.7;color:var(--ink-2);}

.tpa-tobottom{
  position:absolute;right:30px;bottom:128px;width:32px;height:32px;border-radius:50%;
  border:1px solid var(--line-2);background:var(--card);color:var(--ink-2);display:flex;align-items:center;justify-content:center;
  opacity:0;pointer-events:none;transform:translateY(5px);transition:opacity .18s ease,transform .18s ease;
  box-shadow:0 10px 22px -16px rgba(32,36,30,.7);cursor:pointer;z-index:10;
}
body.tpa-scrolled-up .tpa-tobottom{opacity:1;pointer-events:auto;transform:none;}
.tpa-tobottom:hover{border-color:var(--ink);color:var(--ink);}

/* ---------- 登录页 ---------- */
.login-shell{display:grid;grid-template-columns:1.06fr .94fr;min-height:100vh;background:var(--paper);}
.login-art{position:relative;background:var(--ink);color:#F2EBDC;padding:46px 52px 34px;display:flex;flex-direction:column;justify-content:space-between;overflow:hidden;}
.login-art::after{content:"";position:absolute;inset:0;background-image:radial-gradient(rgba(255,255,255,.055) 1px,transparent 1px);background-size:26px 26px;opacity:.5;pointer-events:none;}
.login-brand{display:flex;align-items:center;gap:11px;position:relative;z-index:2;}
.login-brand .tpa-brand-mark{color:#D98A63;}
.login-brand .tpa-brand-name{color:#F6F0E2;}
.login-brand .tpa-brand-sub{color:rgba(242,235,220,.5);}
.login-map{position:absolute;right:-60px;bottom:-40px;width:76%;max-width:720px;height:auto;color:#F2EBDC;opacity:.22;pointer-events:none;z-index:1;}
.login-quote{position:relative;z-index:2;max-width:520px;margin:40px 0;}
.login-kicker{display:flex;align-items:center;gap:10px;font-family:var(--mono);font-size:9px;letter-spacing:.24em;text-transform:uppercase;color:#D98A63;}
.login-kicker::before{content:"";width:26px;height:1px;background:#D98A63;}
.login-quote h1{font-family:var(--serif);font-size:clamp(38px,4.4vw,58px);line-height:1.28;font-weight:500;letter-spacing:.01em;margin:20px 0 18px;color:#F6F0E2;}
.login-quote h1 em{font-style:normal;color:#D98A63;}
.login-quote p{font-size:12.8px;line-height:2;color:rgba(242,235,220,.6);margin:0;max-width:44ch;}
.login-foot{position:relative;z-index:2;display:flex;align-items:center;justify-content:space-between;gap:16px;font-family:var(--mono);font-size:9px;letter-spacing:.12em;color:rgba(242,235,220,.4);text-transform:uppercase;border-top:1px solid rgba(242,235,220,.14);padding-top:16px;}
.login-form-wrap{display:flex;align-items:center;justify-content:center;padding:40px 34px;background:var(--paper);position:relative;}
.login-card{width:100%;max-width:372px;}
.login-card-head{margin-bottom:28px;}
.login-eyebrow{font-family:var(--mono);font-size:9px;letter-spacing:.22em;text-transform:uppercase;color:var(--faint);margin-bottom:10px;}
.login-title{font-family:var(--serif);font-size:32px;line-height:1.25;font-weight:600;color:var(--ink);margin:0 0 8px;}
.login-desc{font-size:12px;line-height:1.75;color:var(--muted);margin:0;}
.auth-tabs{display:flex;gap:26px;border-bottom:1px solid var(--line);margin-bottom:6px;}
.auth-tab{
  position:relative;background:transparent;border:0;padding:0 0 11px;font-size:13px;color:var(--muted);
  cursor:pointer;letter-spacing:.03em;transition:color .15s ease;
}
.auth-tab:hover{color:var(--ink);}
.auth-tab.active{color:var(--ink);font-weight:650;}
.auth-tab.active::after{content:"";position:absolute;left:0;right:0;bottom:-1px;height:2px;background:var(--accent);}
.field{margin-top:21px;}
.field-label{display:flex;align-items:center;justify-content:space-between;font-family:var(--mono);font-size:9px;letter-spacing:.16em;text-transform:uppercase;color:var(--muted);margin-bottom:4px;}
.field .q-field__control{min-height:38px!important;padding:0!important;background:transparent!important;border-bottom:1px solid var(--line-2);border-radius:0!important;transition:border-color .16s ease;}
.field .q-field__control:before,.field .q-field__control:after{display:none!important;}
.field .q-field__native{font-size:14px!important;padding:0 0 7px!important;color:var(--ink)!important;}
.field .q-field__native::placeholder{color:var(--faint)!important;}
.field.q-field--focused .q-field__control{border-bottom-color:var(--accent);}
.field .q-field__append{height:37px;color:var(--faint);}
.field-eye{background:transparent;border:0;color:var(--faint);cursor:pointer;display:flex;align-items:center;padding:4px;border-radius:2px;}
.field-eye:hover{color:var(--ink);}
.auth-error{min-height:20px;margin-top:12px;font-size:11.5px;line-height:1.6;color:var(--danger);display:flex;align-items:flex-start;gap:6px;}
.auth-error::before{content:"!";flex:0 0 13px;width:13px;height:13px;border:1px solid currentColor;border-radius:50%;display:inline-flex;align-items:center;justify-content:center;font-family:var(--mono);font-size:8px;line-height:1;margin-top:2px;}
.auth-error .icon{display:flex;flex:0 0 auto;margin-top:2px;}
.auth-note{margin-top:16px;font-size:11px;line-height:1.7;color:var(--muted);}
.auth-note.closed{padding:10px 12px;background:var(--amber-wash);border:1px solid #E4D2AA;border-radius:2px;color:#6D4E16;}
.auth-submit{
  width:100%;height:44px;margin-top:20px;background:var(--ink);color:#F9F3E6;border:1px solid var(--ink);
  border-radius:2px;font-size:13px;letter-spacing:.12em;display:flex;align-items:center;justify-content:center;gap:10px;
  cursor:pointer;transition:background .18s ease,border-color .18s ease;
}
.auth-submit:hover{background:var(--accent);border-color:var(--accent);}
.auth-submit:disabled{opacity:.6;cursor:wait;}
.auth-foot{margin-top:26px;display:flex;align-items:center;gap:7px;font-family:var(--mono);font-size:9px;letter-spacing:.08em;color:var(--faint);line-height:1.6;text-transform:uppercase;}
.login-mobile-brand{display:none;}

/* ---------- 管理页 ---------- */
.admin-scroll{flex:1;min-height:0;overflow-y:auto;}
.admin-inner{max-width:1040px;margin:0 auto;padding:38px 40px 60px;}
.page-head{display:flex;align-items:flex-end;gap:22px;padding-bottom:18px;border-bottom:1px solid var(--ink);}
.page-head-main{flex:1;min-width:0;}
.page-kicker{display:flex;align-items:center;gap:10px;font-family:var(--mono);font-size:9px;letter-spacing:.22em;text-transform:uppercase;color:var(--accent);margin-bottom:10px;}
.page-kicker::before{content:"";width:22px;height:1px;background:var(--accent);}
.page-title{font-family:var(--serif);font-size:34px;line-height:1.2;font-weight:600;letter-spacing:.005em;color:var(--ink);margin:0;}
.page-sub{margin:7px 0 0;font-size:12px;line-height:1.7;color:var(--muted);}
.page-actions{display:flex;align-items:center;gap:8px;flex:0 0 auto;padding-bottom:3px;}
.btn-ink{
  display:inline-flex;align-items:center;gap:7px;height:36px;padding:0 14px;border-radius:2px;
  background:var(--ink);color:#F9F3E6;border:1px solid var(--ink);font-size:12px;letter-spacing:.03em;cursor:pointer;
  transition:background .16s ease,border-color .16s ease;
}
.btn-ink:hover{background:var(--accent);border-color:var(--accent);}
.btn-ink:disabled{opacity:.5;cursor:not-allowed;}
.btn-ghost{
  display:inline-flex;align-items:center;gap:7px;height:36px;padding:0 13px;border-radius:2px;
  background:transparent;color:var(--ink-2);border:1px solid var(--line-2);font-size:12px;letter-spacing:.02em;cursor:pointer;
  transition:border-color .16s ease,background .16s ease,color .16s ease;
}
.btn-ghost:hover{border-color:var(--ink);color:var(--ink);background:var(--card);}
.btn-ghost:disabled{opacity:.45;cursor:not-allowed;}
.btn-link{background:transparent;border:0;padding:0;color:var(--accent);font-size:11.5px;cursor:pointer;letter-spacing:.01em;}
.btn-link:hover{text-decoration:underline;text-underline-offset:3px;}
.btn-link.muted{color:var(--muted);}
.btn-link.danger{color:var(--danger);}
.btn-link:disabled{opacity:.35;cursor:not-allowed;text-decoration:none;}

.stats{display:flex;gap:26px;flex-wrap:wrap;padding:18px 0 8px;}
.stat{display:flex;flex-direction:column;gap:3px;min-width:74px;}
.stat-num{font-family:var(--serif);font-size:25px;line-height:1.1;color:var(--ink);}
.stat-label{font-family:var(--mono);font-size:8.5px;letter-spacing:.16em;text-transform:uppercase;color:var(--faint);}
.stat-div{width:1px;background:var(--line);align-self:stretch;}

.tpa-table{width:100%;margin-top:18px;border-top:1px solid var(--ink);}
.thead,.trow{display:grid;align-items:center;gap:12px;padding:10px 10px;}
.thead{font-family:var(--mono);font-size:8.5px;letter-spacing:.14em;text-transform:uppercase;color:var(--faint);border-bottom:1px solid var(--line-2);}
.trow{border-bottom:1px solid var(--line);min-height:58px;transition:background .14s ease;}
.trow:hover{background:var(--card);}
.trow.failed{background:rgba(160,58,42,.045);box-shadow:inset 3px 0 0 var(--danger);}
.trow.self{background:rgba(43,86,71,.035);}
.doc-head{grid-template-columns:minmax(0,2.5fr) 64px 86px 56px 112px 74px;}
.doc-row{grid-template-columns:minmax(0,2.5fr) 64px 86px 56px 112px 74px;}
.user-head{grid-template-columns:minmax(0,1.3fr) 74px 88px 68px 108px minmax(190px,auto);}
.user-row{grid-template-columns:minmax(0,1.3fr) 74px 88px 68px 108px minmax(190px,auto);}
.skeleton-row{display:flex;align-items:center;gap:14px;padding:17px 10px;border-bottom:1px solid var(--line);}
.skeleton-bar{height:9px;background:linear-gradient(90deg,var(--paper-deep),var(--paper),var(--paper-deep));background-size:200% 100%;animation:tpaSkeleton 1.4s ease-in-out infinite;border-radius:2px;}
@keyframes tpaSkeleton{0%{background-position:200% 0;}100%{background-position:-200% 0;}}
.cell{min-width:0;}
.cell-title{font-size:12.5px;font-weight:650;color:var(--ink);line-height:1.45;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;}
.cell-sub{font-family:var(--mono);font-size:9.5px;color:var(--muted);margin-top:3px;line-height:1.5;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;}
.cell-sub.error{color:var(--danger);white-space:normal;}
.mobile-meta{display:none;font-family:var(--mono);font-size:9.5px;line-height:1.65;color:var(--muted);margin-top:5px;}
.cell-mono{font-family:var(--mono);font-size:10.5px;color:var(--ink-2);letter-spacing:.02em;}
.cell-muted{font-family:var(--mono);font-size:10px;color:var(--muted);}
.row-actions{display:flex;align-items:center;gap:11px;}
.badge{
  display:inline-flex;align-items:center;gap:5px;padding:2px 7px;border:1px solid var(--line-2);border-radius:99px;
  font-family:var(--mono);font-size:8.5px;letter-spacing:.08em;text-transform:uppercase;color:var(--ink-2);background:var(--card);line-height:1.5;
}
.badge.ok{border-color:#B7CBB7;background:var(--pine-wash);color:var(--ok);}
.badge.fail{border-color:#E0BDB2;background:var(--danger-wash);color:var(--danger);}
.badge.pending{border-color:#E4D2AA;background:var(--amber-wash);color:#7C5A18;}
.badge.root{border-color:#B7CBB7;background:var(--pine-wash);color:var(--pine);}
.badge-dot{width:5px;height:5px;border-radius:50%;background:currentColor;display:inline-block;}
.status-text{display:inline-flex;align-items:center;gap:5px;font-family:var(--mono);font-size:9.5px;letter-spacing:.04em;color:var(--ink-2);}
.status-text.disabled{color:var(--danger);}
.status-text.active{color:var(--ok);}
.status-dot{width:5px;height:5px;border-radius:50%;background:currentColor;}
.self-tag{display:inline-flex;align-items:center;font-family:var(--mono);font-size:8px;letter-spacing:.08em;color:var(--pine);border:1px solid #B7CBB7;background:var(--pine-wash);padding:1px 4px;border-radius:1px;margin-left:5px;flex:0 0 auto;}
.user-row .cell-title{display:flex;align-items:center;gap:6px;overflow:hidden;}

.empty-box{
  margin-top:22px;border:1px dashed var(--line-2);background:rgba(255,253,247,.5);
  padding:52px 26px;text-align:center;border-radius:2px;
}
.empty-icon{width:38px;height:38px;margin:0 auto 14px;color:var(--line-2);display:flex;align-items:center;justify-content:center;}
.empty-title{font-family:var(--serif);font-size:18px;color:var(--ink);margin:0 0 7px;}
.empty-text{font-size:12px;line-height:1.75;color:var(--muted);margin:0 auto;max-width:44ch;}
.empty-actions{margin-top:17px;display:flex;justify-content:center;gap:8px;}

.search-panel{margin-top:34px;border-top:1px solid var(--line);padding-top:24px;}
.panel-kicker{font-family:var(--mono);font-size:9px;letter-spacing:.18em;text-transform:uppercase;color:var(--faint);margin-bottom:6px;}
.panel-title{font-family:var(--serif);font-size:20px;color:var(--ink);margin:0 0 6px;}
.panel-desc{font-size:11.5px;line-height:1.7;color:var(--muted);margin:0 0 16px;}
.search-bar{display:flex;align-items:flex-end;gap:10px;max-width:600px;}
.search-input{flex:1;}
.search-input .q-field__control{min-height:36px!important;padding:0!important;background:transparent!important;border-bottom:1px solid var(--line-2);border-radius:0!important;}
.search-input .q-field__control:before,.search-input .q-field__control:after{display:none!important;}
.search-input .q-field__native{font-size:13px!important;padding:0 0 7px!important;}
.search-input.q-field--focused .q-field__control{border-bottom-color:var(--accent);}
.search-meta{display:flex;align-items:center;gap:8px;margin:14px 0 10px;font-family:var(--mono);font-size:9.5px;color:var(--muted);letter-spacing:.03em;}
.search-results{display:flex;flex-direction:column;gap:9px;margin-top:12px;}
.hit{border:1px solid var(--line);background:var(--card);border-radius:2px;padding:12px 14px;}
.hit-head{display:flex;align-items:center;gap:8px;flex-wrap:wrap;}
.hit-title{font-size:12px;font-weight:650;color:var(--ink);}
.hit-meta{font-family:var(--mono);font-size:9px;color:var(--faint);}
.hit-score{margin-left:auto;font-family:var(--mono);font-size:9.5px;color:var(--accent);}
.hit-snippet{margin:7px 0 0;font-size:11.5px;line-height:1.75;color:var(--ink-2);}
.search-empty{font-size:11.5px;color:var(--muted);padding:12px 0;line-height:1.7;}
.search-loading{display:flex;align-items:center;gap:8px;font-family:var(--mono);font-size:9.5px;color:var(--muted);padding:12px 0;}

/* ---------- 弹窗 ---------- */
.dialog-card{padding:24px 26px 20px;min-width:min(420px,88vw);}
.dialog-card .field,.dialog-card .field .q-field,.dialog-card .dialog-field{width:100%;}
.dialog-title{font-family:var(--serif);font-size:22px;line-height:1.3;color:var(--ink);margin:0 0 5px;font-weight:600;}
.dialog-sub{font-size:11.5px;line-height:1.7;color:var(--muted);margin:0 0 18px;}
.dialog-actions{display:flex;align-items:center;justify-content:flex-end;gap:8px;margin-top:22px;width:100%;}
.dialog-actions .spacer{flex:1;}
.dialog-field .q-field__control{min-height:40px!important;background:var(--surface)!important;border:1px solid var(--line-2);border-radius:2px!important;padding:0 11px!important;}
.dialog-field .q-field__control:before,.dialog-field .q-field__control:after{display:none!important;}
.dialog-field .q-field__native{font-size:13px!important;}
.dialog-field.q-field--focused .q-field__control{border-color:var(--accent);}
.dialog-field .q-field__label{font-size:11px!important;}
.dialog-field textarea{min-height:70px;}
.dialog-note{margin-top:12px;font-size:10.5px;line-height:1.7;color:var(--faint);}
.profile-grid{display:grid;grid-template-columns:1fr 1fr;gap:12px 14px;margin-top:4px;}
.profile-grid .wide{grid-column:1 / -1;}
.profile-grid .q-field__control{min-height:38px!important;background:var(--surface)!important;border:1px solid var(--line-2);border-radius:2px!important;padding:0 10px!important;}
.profile-grid .q-field__control:before,.profile-grid .q-field__control:after{display:none!important;}
.profile-grid .q-field__native,.profile-grid .q-chip{font-size:12px!important;}
.profile-grid .q-field--focused .q-field__control{border-color:var(--accent);}
.q-chip{background:var(--paper-deep)!important;color:var(--ink-2)!important;font-size:10px!important;min-height:22px!important;border-radius:2px!important;}
.q-chip .q-chip__icon--remove{font-size:14px!important;}
.preview-chunks{display:flex;flex-direction:column;gap:8px;margin-top:14px;max-height:320px;overflow-y:auto;}
.preview-chunk{border-left:2px solid var(--line-2);padding:6px 10px;font-size:11px;line-height:1.75;color:var(--ink-2);background:var(--paper);}
.preview-chunk .idx{font-family:var(--mono);font-size:8.5px;color:var(--faint);display:block;margin-bottom:2px;}
.processing{display:flex;flex-direction:column;align-items:center;text-align:center;padding:8px 4px 4px;}
.processing .ring{width:34px;height:34px;border:2px solid var(--line);border-top-color:var(--accent);border-radius:50%;animation:tpaSpin .8s linear infinite;margin-bottom:16px;}
.processing .title{font-family:var(--serif);font-size:18px;color:var(--ink);margin:0 0 6px;}
.processing .text{font-size:11.5px;line-height:1.7;color:var(--muted);margin:0 0 14px;max-width:34ch;}
.progress-line{width:100%;height:2px;background:var(--line);overflow:hidden;position:relative;}
.progress-line::after{content:"";position:absolute;left:-40%;top:0;bottom:0;width:40%;background:var(--accent);animation:tpaIndet 1.3s ease-in-out infinite;}
@keyframes tpaIndet{0%{left:-40%;}100%{left:100%;}}

.upload-box{border:1px dashed var(--line-2);background:var(--surface);border-radius:2px;padding:18px;text-align:center;}
.upload-box .q-uploader{width:100%!important;background:transparent!important;box-shadow:none!important;border:0!important;}
.upload-box .q-uploader__header{background:transparent!important;color:var(--ink)!important;border:0!important;box-shadow:none!important;padding:0!important;min-height:0!important;}
.upload-box .q-uploader__header-content{color:var(--ink-2)!important;font-size:12px!important;padding:0!important;}
.upload-box .q-uploader__list{background:transparent!important;color:var(--ink-2)!important;padding:6px 0 0!important;min-height:0!important;}
.upload-box .q-uploader__subtitle{display:none!important;}
.upload-box .q-uploader__dnd{color:var(--ink-2)!important;font-size:12px!important;}
.upload-box .q-btn{color:var(--ink-2)!important;}
.upload-box .q-uploader__list .q-item{border-bottom:1px solid var(--line)!important;min-height:36px!important;}

.status-list{display:flex;flex-direction:column;gap:0;margin-top:12px;border-top:1px solid var(--line);}
.status-row{display:flex;align-items:center;gap:10px;padding:9px 2px;border-bottom:1px solid var(--line);font-size:11.5px;}
.status-row .name{font-family:var(--mono);font-size:10.5px;color:var(--ink);min-width:130px;}
.status-row .desc{flex:1;min-width:0;font-size:11px;color:var(--muted);overflow:hidden;text-overflow:ellipsis;white-space:nowrap;}
.status-row .badge{flex:0 0 auto;}
.invoke-box{margin-top:16px;border-top:1px solid var(--line);padding-top:14px;}
.invoke-box .q-field__control{min-height:36px!important;background:var(--surface)!important;border:1px solid var(--line-2);border-radius:2px!important;padding:0 10px!important;}
.invoke-box .q-field__control:before,.invoke-box .q-field__control:after{display:none!important;}
.invoke-out{margin-top:10px;font-family:var(--mono);font-size:9.5px;line-height:1.65;color:var(--ink-2);background:var(--paper);border:1px solid var(--line);padding:9px 11px;max-height:170px;overflow:auto;white-space:pre-wrap;word-break:break-all;}

.note{font-size:10.5px;line-height:1.7;color:var(--faint);}
.tpa-scrim{display:none;position:fixed;inset:0;background:rgba(28,32,26,.4);z-index:35;backdrop-filter:blur(2px);}

/* ---------- 响应式 ---------- */
@media (max-width:1120px){
  .login-art{padding:40px 38px 30px;}
  .login-quote h1{font-size:clamp(34px,4.2vw,46px);}
}
@media (max-width:960px){
  .tpa-sidebar{position:fixed;left:0;top:0;bottom:0;transform:translateX(-100%);transition:transform .24s ease;box-shadow:18px 0 50px -34px rgba(20,24,18,.7);}
  body.tpa-nav-open .tpa-sidebar{transform:none;}
  body.tpa-nav-open .tpa-scrim{display:block;}
  .tpa-menu-btn{display:inline-flex!important;}
  .tpa-topbar{padding:0 16px;gap:8px;}
  .tpa-chat-inner{padding:26px 20px 20px;}
  .tpa-composer-wrap{padding:8px 16px 14px;}
  .tpa-thinking{padding:0 16px;}
  .tpa-banner{padding:8px 16px;}
  .tpa-tobottom{right:18px;bottom:122px;}
  .admin-inner{padding:28px 20px 48px;}
  .page-head{flex-direction:column;align-items:flex-start;gap:14px;}
  .page-actions{width:100%;}
  .thead{display:none;}
  .trow{grid-template-columns:minmax(0,1fr) max-content!important;gap:6px 12px;padding:13px 6px;}
  .trow .cell{grid-column:1;}
  .trow .cell-hide{display:none;}
  .trow .row-actions{grid-column:2;grid-row:1;align-self:start;justify-self:end;width:max-content;}
  .doc-row .cell:nth-child(n+2):not(.row-actions),.user-row .cell:nth-child(n+2):not(.row-actions){display:none;}
  .doc-row .row-actions,.user-row .row-actions{display:flex;}
  .mobile-meta{display:block;}
  .stats{display:grid;grid-template-columns:1fr 1fr;gap:14px 22px;}
  .stat-div{display:none;}
  .prompt-grid{grid-template-columns:1fr;gap:8px;}
  .prompt-card{min-height:0;flex-direction:row;align-items:center;gap:12px;padding:12px 14px;}
  .prompt-text{flex:1;}
  .prompt-top{flex:0 0 auto;}
  .prompt-arrow{display:none;}
  .login-shell{grid-template-columns:1fr;}
  .login-art{min-height:300px;padding:28px 24px 22px;}
  .login-map{width:110%;right:-34%;bottom:-24%;opacity:.16;}
  .login-quote{margin:26px 0 6px;max-width:100%;}
  .login-quote h1{font-size:34px;margin:13px 0 10px;}
  .login-quote p{display:none;}
  .login-foot{display:none;}
  .login-form-wrap{padding:30px 24px 44px;}
  .login-card{max-width:440px;}
  .login-mobile-brand{display:none;}
  .trip-head{padding:18px 18px 14px;}
  .trip-title{font-size:21px;}
  .trip-head-top{flex-direction:column;gap:10px;}
  .trip-export{align-self:flex-start;}
  .budget{padding:14px 18px;}
  .day-head{padding:12px 18px;}
  .day-body{padding:2px 18px 10px;}
  .stop{grid-template-columns:70px 14px minmax(0,1fr);gap:0 9px;}
  .trip-risks,.trip-pack{padding-left:18px;padding-right:18px;}
  .profile-grid{grid-template-columns:1fr;}
  .msg-user-box{max-width:88%;}
  .tpa-chat-inner{padding-bottom:14px;}
}
@media (max-width:520px){
  .login-art{min-height:250px;}
  .login-quote h1{font-size:29px;}
  .login-kicker{font-size:8px;}
  .tpa-hero h1{font-size:31px;line-height:1.3;}
  .tpa-hero h1 em{display:block;}
  .topbar-sub{display:none;}
  .msg-actions{opacity:1;}
  .trip-sub{font-size:9px;}
  .day-index{min-width:28px;font-size:21px;}
  .stop{grid-template-columns:58px 12px minmax(0,1fr);gap:0 7px;}
  .stop-time{font-size:9.5px;}
  .tool-row{grid-template-columns:14px minmax(0,1.1fr) 42px minmax(0,1fr);}
  .tool-server{display:none;}
  .tpa-tobottom{bottom:118px;}
  .dialog-card{padding:20px 18px 16px;}
  .auth-tabs{gap:20px;}
}
@media (prefers-reduced-motion:reduce){
  *,*::before,*::after{animation-duration:.001ms!important;animation-iteration-count:1!important;transition-duration:.001ms!important;scroll-behavior:auto!important;}
}
"""

# 行内线性图标：比默认的 Material 实心图标更接近印刷品
_ICON_PATHS: dict[str, str] = {
    "arrow-up": '<path d="M12 19V5"/><path d="m5 12 7-7 7 7"/>',
    "stop": '<rect x="7" y="7" width="10" height="10" rx="1.2" fill="currentColor" stroke="none"/>',
    "arrow-right": '<path d="M5 12h14"/><path d="m12 5 7 7-7 7"/>',
    "arrow-down": '<path d="M12 5v14"/><path d="m19 12-7 7-7-7"/>',
    "chevron-right": '<path d="m9 18 6-6-6-6"/>',
    "chevron-down": '<path d="m6 9 6 6 6-6"/>',
    "plus": '<path d="M12 5v14"/><path d="M5 12h14"/>',
    "more": '<circle cx="5" cy="12" r="1.2" fill="currentColor" stroke="none"/><circle cx="12" cy="12" r="1.2" fill="currentColor" stroke="none"/><circle cx="19" cy="12" r="1.2" fill="currentColor" stroke="none"/>',
    "download": '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><path d="m7 10 5 5 5-5"/><path d="M12 15V3"/>',
    "copy": '<rect x="9" y="9" width="12" height="12" rx="2"/><path d="M5 15H4a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1h10a1 1 0 0 1 1 1v1"/>',
    "refresh": '<path d="M20 11a8 8 0 1 0-.6 4"/><path d="M20 4v7h-7"/>',
    "close": '<path d="M18 6 6 18"/><path d="m6 6 12 12"/>',
    "trash": '<path d="M3 6h18"/><path d="M8 6V4h8v2"/><path d="M19 6l-1 14H6L5 6"/><path d="M10 11v5"/><path d="M14 11v5"/>',
    "upload": '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><path d="m7 8 5-5 5 5"/><path d="M12 3v12"/>',
    "link": '<path d="M10 13a5 5 0 0 0 7.1 0l2-2a5 5 0 0 0-7.1-7.1L10.6 5.3"/><path d="M14 11a5 5 0 0 0-7.1 0l-2 2a5 5 0 0 0 7.1 7.1l1.4-1.4"/>',
    "search": '<circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/>',
    "menu": '<path d="M4 7h16"/><path d="M4 12h16"/><path d="M4 17h16"/>',
    "settings": '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .34 1.87l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06A1.7 1.7 0 0 0 15 19.4a1.7 1.7 0 0 0-1 1.55V21a2 2 0 1 1-4 0v-.09A1.7 1.7 0 0 0 9 19.4a1.7 1.7 0 0 0-1.87.34l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06A1.7 1.7 0 0 0 4.6 15a1.7 1.7 0 0 0-1.55-1H3a2 2 0 1 1 0-4h.09A1.7 1.7 0 0 0 4.6 9a1.7 1.7 0 0 0-.34-1.87l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06A1.7 1.7 0 0 0 9 4.6a1.7 1.7 0 0 0 1-1.55V3a2 2 0 1 1 4 0v.09a1.7 1.7 0 0 0 1 1.55 1.7 1.7 0 0 0 1.87-.34l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06A1.7 1.7 0 0 0 19.4 9c.12.42.45.76.87.88H21a2 2 0 1 1 0 4h-.09a1.7 1.7 0 0 0-1.55 1Z"/>',
    "logout": '<path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><path d="m16 17 5-5-5-5"/><path d="M21 12H9"/>',
    "user": '<circle cx="12" cy="8" r="4"/><path d="M4 21a8 8 0 0 1 16 0"/>',
    "users": '<circle cx="9" cy="8" r="3.5"/><path d="M2.5 21a6.5 6.5 0 0 1 13 0"/><path d="M16 4.5a3.5 3.5 0 0 1 0 7"/><path d="M18.5 14.3A6.5 6.5 0 0 1 22 21"/>',
    "book": '<path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2Z"/><path d="M8 7h8"/><path d="M8 11h6"/>',
    "chat": '<path d="M21 11.5a8.4 8.4 0 0 1-9 8.4 9 9 0 0 1-3.4-.7L3 21l1.8-4.6A8.4 8.4 0 0 1 4 11.5a8.4 8.4 0 0 1 8.5-8.4 8.4 8.4 0 0 1 8.5 8.4Z"/>',
    "check": '<path d="m5 12 5 5L20 7"/>',
    "x": '<path d="M18 6 6 18"/><path d="m6 6 12 12"/>',
    "clock": '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
    "pin": '<path d="M12 21s7-6.1 7-11a7 7 0 1 0-14 0c0 4.9 7 11 7 11Z"/><circle cx="12" cy="10" r="2.5"/>',
    "warn": '<path d="M12 3 2.5 20h19L12 3Z"/><path d="M12 9v5"/><path d="M12 17.2v.2"/>',
    "suitcase": '<rect x="3" y="7" width="18" height="13" rx="2"/><path d="M8 7V5a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/><path d="M3 12h18"/>',
    "weather": '<path d="M17.5 19a4.5 4.5 0 0 0 .4-9 6 6 0 0 0-11.7-1.4A4 4 0 0 0 6.5 19h11Z"/>',
    "eye": '<path d="M2 12s3.5-6 10-6 10 6 10 6-3.5 6-10 6S2 12 2 12Z"/><circle cx="12" cy="12" r="2.5"/>',
    "eye-off": '<path d="m3 3 18 18"/><path d="M10.6 6.2A10.7 10.7 0 0 1 12 6c6.5 0 10 6 10 6a17 17 0 0 1-3 3.6"/><path d="M6.2 6.7A16.7 16.7 0 0 0 2 12s3.5 6 10 6a10.6 10.6 0 0 0 4.1-.8"/><path d="M9.9 9.9a3 3 0 0 0 4.2 4.2"/>',
    "compass": '<circle cx="12" cy="12" r="9"/><path d="m15.5 8.5-2 5-5 2 2-5 5-2Z"/>',
    "download-cloud": '<path d="M12 13v8"/><path d="m8 17 4 4 4-4"/><path d="M20 16.7A4.5 4.5 0 0 0 17.5 8h-1.3A6 6 0 0 0 4.6 10.5 4 4 0 0 0 6 18.4"/>',
    "spark": '<path d="M12 2v4"/><path d="M12 18v4"/><path d="m4.9 4.9 2.8 2.8"/><path d="m16.3 16.3 2.8 2.8"/><path d="M2 12h4"/><path d="M18 12h4"/><path d="m4.9 19.1 2.8-2.8"/><path d="m16.3 7.7 2.8-2.8"/>',
    "code": '<path d="m8 6-6 6 6 6"/><path d="m16 6 6 6-6 6"/>',
    "route": '<circle cx="6" cy="19" r="2.5"/><circle cx="18" cy="5" r="2.5"/><path d="M8.5 19H15a4 4 0 0 0 0-8H9a4 4 0 0 1 0-8h1.5"/>',
    "walk": '<circle cx="13" cy="4.5" r="1.8"/><path d="m10 21 2.2-6.2L9 12l1.6-4.4L14 9l2.6 1.2"/><path d="m14.4 14.6 2.1 6.4"/><path d="M9 12 6.5 21"/>',
    "car": '<path d="M5 17h14"/><path d="m6 17-1.2-5.2A2 2 0 0 1 6.7 9h10.6a2 2 0 0 1 1.9 2.8L18 17"/><path d="M6 17v2"/><path d="M18 17v2"/><circle cx="8" cy="14" r="1"/><circle cx="16" cy="14" r="1"/>',
    "transit": '<rect x="5" y="3" width="14" height="14" rx="3"/><path d="M5 11h14"/><path d="M8 21l2-4"/><path d="M16 21l-2-4"/><circle cx="8.5" cy="14" r=".8" fill="currentColor" stroke="none"/><circle cx="15.5" cy="14" r=".8" fill="currentColor" stroke="none"/>',
}


def icon_svg(name: str, size: int = 17, stroke: float = 1.6) -> str:
    paths = _ICON_PATHS.get(name, _ICON_PATHS["compass"])
    return (
        f'<svg width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" '
        f'stroke="currentColor" stroke-width="{stroke}" stroke-linecap="round" '
        f'stroke-linejoin="round" aria-hidden="true">{paths}</svg>'
    )


def icon(name: str, size: int = 17, classes: str = "") -> Any:
    return ui.html(icon_svg(name, size)).classes(classes)


def brand_mark(size: int = 34) -> str:
    """一个「路线 + 两个端点」的标记，比圆形字母 logo 更像旅行产品。"""
    return f"""<svg width="{size}" height="{size}" viewBox="0 0 40 40" fill="none" aria-hidden="true">
      <rect x="1.5" y="1.5" width="37" height="37" rx="19" stroke="currentColor" stroke-width="1.2" opacity=".38"/>
      <path d="M11 28.5c4.4 0 5.6-6.1 9.2-9.7 2.6-2.6 5.4-3.4 8.6-3.4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
      <circle cx="11" cy="28.5" r="2.6" fill="#FAF7EF" stroke="currentColor" stroke-width="1.5"/>
      <circle cx="28.8" cy="15.4" r="2.6" fill="currentColor"/>
      <path d="M23.5 12.2h7.6v7.6" stroke="currentColor" stroke-width="1.1" stroke-linecap="round" opacity=".55"/>
    </svg>"""


LOGIN_MAP_SVG = """
<svg class="login-map" viewBox="0 0 720 780" fill="none" aria-hidden="true">
  <g stroke="currentColor" stroke-width="1" opacity=".55">
    <path d="M-40 690C90 612 146 470 116 340 96 254 24 214-20 130"/>
    <path d="M760 618C624 560 566 418 606 300c30-88 104-118 154-196"/>
    <path d="M118 810c30-150 126-236 244-246 116-10 202 62 302 20"/>
    <path d="M-20 250c110 4 176 62 214 146 34 74 20 170 84 234 72 72 202 50 272 118"/>
    <path d="M40 520c128-20 234 28 322 108 72 66 122 160 250 178"/>
    <path d="M330 40c-22 108 20 190 96 240 82 54 180 54 250 132"/>
  </g>
  <g stroke="currentColor" stroke-width="1.4" stroke-dasharray="4 7" opacity=".75">
    <path d="M182 628C232 536 208 430 286 360c82-72 200-40 244-126 30-58 22-128 2-188"/>
  </g>
  <g fill="currentColor">
    <circle cx="182" cy="628" r="5"/>
    <circle cx="532" cy="234" r="5"/>
    <circle cx="286" cy="360" r="3" opacity=".65"/>
    <circle cx="392" cy="584" r="3" opacity=".5"/>
  </g>
  <g font-family="monospace" font-size="12" letter-spacing="3" fill="currentColor" opacity=".8">
    <text x="204" y="652">HANGZHOU</text>
    <text x="470" y="212">SUZHOU</text>
  </g>
  <g stroke="currentColor" opacity=".22">
    <path d="M60 86h54M60 86v54"/>
    <path d="M660 694h-54M660 694v-54"/>
  </g>
</svg>
"""

JS = r"""
window.tpaBindScroll = function(){
  const el = document.getElementById('tpaChatScroll');
  if(!el || el.dataset.bound){ return; }
  el.dataset.bound = '1';
  const update = () => {
    const near = el.scrollHeight - el.scrollTop - el.clientHeight < 100;
    document.body.classList.toggle('tpa-scrolled-up', !near && el.scrollHeight > el.clientHeight + 120);
  };
  el.addEventListener('scroll', update, {passive:true});
  update();
};
window.tpaScrollBottom = function(smooth){
  const el = document.getElementById('tpaChatScroll');
  if(!el){ return; }
  el.scrollTo({top: el.scrollHeight, behavior: smooth ? 'smooth' : 'auto'});
  document.body.classList.remove('tpa-scrolled-up');
};
window.tpaAutoScroll = function(){
  const el = document.getElementById('tpaChatScroll');
  if(!el){ return; }
  const near = el.scrollHeight - el.scrollTop - el.clientHeight < 100;
  if(near){ el.scrollTop = el.scrollHeight; }
};
window.tpaScrollToLastAssistant = function(){
  const el = document.getElementById('tpaChatScroll');
  if(!el){ return; }
  const nodes = el.querySelectorAll('.msg-assistant');
  if(!nodes.length){ el.scrollTop = el.scrollHeight; return; }
  const node = nodes[nodes.length - 1];
  const top = node.getBoundingClientRect().top - el.getBoundingClientRect().top + el.scrollTop;
  el.scrollTop = Math.max(0, top - 22);
  document.body.classList.remove('tpa-scrolled-up');
};
window.tpaBindComposer = function(){
  const root = document.getElementById('tpaComposer');
  if(!root || root.dataset.bound){ return; }
  root.dataset.bound = '1';
  const ta = root.querySelector('textarea');
  if(!ta){ return; }
  ta.addEventListener('keydown', (event) => {
    if(event.key === 'Enter' && !event.shiftKey && !event.isComposing){
      event.preventDefault();
      const btn = document.getElementById('tpaSendBtn');
      if(btn){ btn.click(); }
    }
  });
};
window.tpaBindTextarea = function(){
  window.tpaBindComposer();
  window.tpaBindScroll();
};
window.tpaCaret = function(id, on){
  const root = document.getElementById(id);
  if(!root){ return; }
  root.querySelectorAll('.tpa-caret').forEach((n) => n.remove());
  if(!on){ return; }
  let target = root.lastElementChild;
  if(!target || ['UL','OL','TABLE','PRE'].includes(target.tagName)){
    target = root;
  }
  const caret = document.createElement('span');
  caret.className = 'tpa-caret';
  target.appendChild(caret);
};
window.tpaToggleNav = function(open){
  document.body.classList.toggle('tpa-nav-open', open === undefined ? !document.body.classList.contains('tpa-nav-open') : open);
};
window.tpaFocus = function(selector){
  const el = document.querySelector(selector);
  if(el){ el.focus(); }
};
"""


def apply_theme() -> None:
    ui.colors(
        primary="#AE4A27",
        secondary="#2B5647",
        accent="#A1752A",
        dark="#20241E",
        positive="#3D6448",
        negative="#A03A2A",
        info="#2B5647",
        warning="#A1752A",
    )
    ui.add_head_html(
        "<meta name=\"theme-color\" content=\"#F4EFE3\">"
        "<meta name=\"description\" content=\"出行计划智能助手 · 从一句想法到一份可执行的行程\">"
    )
    ui.add_head_html(f"<style>{CSS}</style>")
    ui.add_head_html(f"<script>{JS}</script>")


def escape(value: Any) -> str:
    return html.escape(str(value if value is not None else ""), quote=True)


def safe_class(value: str) -> str:
    return "".join(ch for ch in value if ch.isalnum() or ch in "-_")
