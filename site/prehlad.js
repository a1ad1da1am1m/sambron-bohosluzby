"use strict";

const get = (id) => document.getElementById(id);
const townFilter = get("town");
const periodFilter = get("period");
const zone = "Europe/Bratislava";
const clock = new Intl.DateTimeFormat("sk-SK", {
  timeZone: zone, year: "numeric", month: "2-digit", day: "2-digit",
  hour: "2-digit", minute: "2-digit", hourCycle: "h23",
});
const fullDate = new Intl.DateTimeFormat("sk-SK", {
  weekday: "long", day: "numeric", month: "long", timeZone: "UTC",
});
const shortDate = new Intl.DateTimeFormat("sk-SK", {
  day: "numeric", month: "numeric", year: "numeric", timeZone: "UTC",
});
const weekday = new Intl.DateTimeFormat("sk-SK", { weekday: "short", timeZone: "UTC" });
const monthDay = new Intl.DateTimeFormat("sk-SK", { day: "numeric", month: "numeric", timeZone: "UTC" });
const format = (formatter, date) => formatter.format(new Date(date + "T12:00:00Z"));
let schedules = [];
let renderedDate;

function element(tag, text = "", className = "") {
  const node = document.createElement(tag);
  node.textContent = text;
  node.className = className;
  return node;
}

function localClock() {
  const fields = Object.fromEntries(clock.formatToParts(new Date()).map(({ type, value }) => [type, value]));
  return { date: fields.year + "-" + fields.month + "-" + fields.day, time: fields.hour + ":" + fields.minute };
}

function scheduleOn(date) {
  return schedules.find((item) => item.start <= date && date <= item.end);
}

function eventsInTown(day) {
  return (day?.events ?? []).filter((event) => !townFilter.value || event.town === townFilter.value);
}

function eventList(events, detailed = false) {
  const list = element("ul", "", detailed ? "events events-detailed" : "events");
  for (const event of events) {
    const item = element("li");
    const time = element("time", event.time);
    time.dateTime = event.time;
    const place = element("span", event.town ?? "Miesto v poriadku nie je uvedené");
    item.append(time);
    if (detailed) {
      const summary = element("div", "", "event-summary");
      summary.append(place);
      if (event.details?.length) {
        const details = element("ul", "", "event-details");
        for (const note of event.details) {
          const kind = /^\(\s*[rd]\s*\./i.test(note) ? "event-donor"
            : /^[+*]/.test(note) ? "event-intention" : "event-note";
          details.append(element("li", note, kind));
        }
        summary.append(details);
      }
      item.append(summary);
    } else {
      item.append(place);
      if (event.label) item.append(element("small", event.label, "event-label"));
    }
    list.append(item);
  }
  return list;
}

function renderSummary(now, active) {
  get("today-date").textContent = format(fullDate, now.date);
  const day = active?.days.find((entry) => entry.date === now.date);
  const events = eventsInTown(day);
  get("today").replaceChildren(events.length ? eventList(events) : element("p",
    day ? day.message ?? "Dnes nie je uvedený termín pre zvolený filter."
      : active ? "V poriadku na dnešný deň nie je uvedený termín." : "Poriadok na dnešný deň zatiaľ nemáme.", "detail"
  ));

  const upcoming = schedules.flatMap((item) => item.days
    .filter((entry) => entry.date >= now.date && scheduleOn(entry.date) === item)
    .flatMap((entry) => eventsInTown(entry).map((event) => ({ ...event, date: entry.date }))))
    .filter((event) => event.date > now.date || event.time >= now.time)
    .sort((a, b) => (a.date + a.time).localeCompare(b.date + b.time));

  const next = get("next");
  const nextDate = get("next-date");
  nextDate.hidden = !upcoming.length;
  if (upcoming.length) {
    const first = upcoming[0];
    nextDate.textContent = format(fullDate, first.date);
    next.replaceChildren(eventList(upcoming.filter((event) => event.date === first.date && event.time === first.time)));
  } else {
    next.replaceChildren(element("p", "V dostupných poriadkoch zatiaľ nie je ďalší termín.", "detail"));
  }
}

function render(now = localClock()) {
  renderedDate = now.date;
  const active = scheduleOn(now.date);
  const selected = schedules.find((item) => item.source === periodFilter.value) ?? active;
  renderSummary(now, active);
  const target = get("schedule");
  const days = get("days");
  days.replaceChildren();
  days.hidden = true;
  target.replaceChildren();
  get("range").textContent = selected
    ? format(shortDate, selected.start) + " – " + format(shortDate, selected.end)
    : "";
  if (!selected) {
    target.append(element("p", "Aktuálny poriadok zatiaľ nemáme. Tu sa zobrazí po načítaní z farskej stránky.", "notice"));
    return;
  }

  if (selected.dateNote) target.append(element("p", selected.dateNote, "schedule-note"));
  const span = (new Date(selected.end) - new Date(selected.start)) / 86_400_000 + 1;
  if (selected.days.length < span) {
    target.append(element("p", "Prehľad uvádza dni, ktoré majú vo farskom rozpise vlastný riadok. Ďalšie oznamy sú v origináli.", "schedule-note"));
  }
  let visibleDays = 0;
  for (const day of selected.days) {
    const events = eventsInTown(day);
    if (townFilter.value && !events.length && !day.message) continue;
    const isToday = day.date === now.date;
    const card = element("article", "", isToday ? "day current" : "day");
    card.id = "den-" + day.date;
    card.tabIndex = -1;
    const caption = element("div");
    caption.append(element("h3", format(fullDate, day.date)));
    if (day.feast) caption.append(element("p", day.feast, "detail"));
    if (isToday) caption.append(element("span", "Dnes", "today-tag"));
    const details = element("div");
    details.append(events.length ? eventList(events, true) : element("p", day.message ?? "Čas nie je uvedený.", "detail"));
    if (day.notes.length) {
      const notes = element("ul", "", "notes");
      for (const note of day.notes) notes.append(element("li", note));
      details.append(element("p", "Poznámky k dňu", "notes-heading"), notes);
    }
    card.append(caption, details);
    target.append(card);
    const dayLink = element("a", "", "day-link");
    dayLink.href = "#" + card.id;
    dayLink.setAttribute("aria-label", format(fullDate, day.date));
    if (isToday) dayLink.setAttribute("aria-current", "date");
    dayLink.append(element("span", format(weekday, day.date)), element("strong", format(monthDay, day.date)));
    days.append(dayLink);
    visibleDays++;
  }

  days.hidden = !visibleDays;
  if (!visibleDays) {
    target.append(element("p", "Vo vybranom poriadku sa nenašiel termín pre túto obec.", "notice"));
  }
  const source = element("a", "Otvoriť pôvodný farský poriadok ↗", "source-link");
  source.href = selected.source;
  target.append(source);
}

function safeLink(value) {
  try {
    const url = new URL(value);
    return ["http:", "https:"].includes(url.protocol) ? url.href : null;
  } catch { return null; }
}

function renderAnnouncements(items) {
  const target = get("announcements");
  target.replaceChildren();
  get("oznamy").hidden = !items.length;
  const now = localClock().date;
  const recentDate = new Date(now + "T12:00:00Z");
  recentDate.setUTCDate(recentDate.getUTCDate() - 14);
  const recent = items.find(item => item.published && item.published >= recentDate.toISOString().slice(0,10) && item.published <= now);
  const shortcut = get("notice-shortcut");
  shortcut.replaceChildren();
  shortcut.hidden = !recent;
  if (recent) {
    const link = element("a", "Z farského webu: " + recent.title + " →");
    link.href = "#oznamy";
    shortcut.append(link, element("span", "Zverejnené " + format(shortDate, recent.published)));
  }
  const cutoff = new Date(now + "T12:00:00Z");
  cutoff.setUTCDate(cutoff.getUTCDate() - 45);
  const cutoffDate = cutoff.toISOString().slice(0, 10);
  for (const item of items) {
    const card = element("details", "", "announcement");
    const summary = element("summary", item.title);
    const dated = /^\d{4}-\d{2}-\d{2}$/.test(item.published ?? "");
    const older = dated && item.published < cutoffDate;
    summary.append(element("span", dated
      ? "Zverejnené " + format(shortDate, item.published) + (older ? " · Starší oznam" : "")
      : "Dátum zverejnenia nie je uvedený", "announcement-meta"));
    card.open = dated && !older;
    const body = element("div", "", "announcement-body");
    for (const text of item.paragraphs ?? []) body.append(element("p", text));
    const media = element("div", "", "announcement-media");
    for (const image of item.images ?? []) {
      const url = safeLink(image.url);
      if (!url) continue;
      const link = element("a"); link.href = url;
      const img = document.createElement("img");
      img.src = url; img.alt = image.alt || "Obrázok k oznamu";
      img.loading = "lazy";
      link.append(img); media.append(link);
    }
    for (const attachment of item.links ?? []) {
      const url = safeLink(attachment.url);
      if (!url) continue;
      const link = element("a", attachment.title || "Otvoriť prílohu");
      link.href = url; media.append(link);
    }
    body.append(media);
    const source = element("a", "Otvoriť pôvodný oznam ↗", "source-link");
    const url = safeLink(item.source);
    if (url) { source.href = url; body.append(source); }
    card.append(summary, body); target.append(card);
  }
}

async function init() {
  try {
    const response = await fetch("./poriadky.json");
    if (!response.ok) throw new Error(String(response.status));
    const data = await response.json();
    schedules = data.schedules ?? [];
    renderAnnouncements(data.announcements ?? []);
    for (const item of schedules) {
      const label = format(shortDate, item.start) + " – " + format(shortDate, item.end);
      periodFilter.add(new Option(label, item.source));
    }
    townFilter.addEventListener("change", () => render());
    periodFilter.addEventListener("change", () => render());
    render();
    if (location.hash.startsWith("#den-")) {
      get(location.hash.slice(1))?.scrollIntoView();
    }
    setInterval(() => {
      const now = localClock();
      if (now.date !== renderedDate) render(now);
      else renderSummary(now, scheduleOn(now.date));
    }, 60_000);
  } catch (error) {
    get("today").textContent = "Rozpis sa nepodarilo načítať.";
    get("next").textContent = "Údaje sú dočasne nedostupné.";
    get("schedule").append(element("p", "Skúste obnoviť stránku alebo otvorte farský originál nižšie.", "notice"));
    console.error(error);
  }
}

init();
