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
const format = (formatter, date) => formatter.format(new Date(date + "T12:00:00Z"));
let schedules = [];

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

function eventList(events) {
  const list = element("ul", "", "events");
  for (const event of events) {
    const item = element("li");
    const time = element("time", event.time);
    time.dateTime = event.time;
    item.append(time, " " + event.town);
    list.append(item);
  }
  return list;
}

function renderSummary(now, active) {
  get("today-date").textContent = "· " + format(shortDate, now.date);
  const day = active?.days.find((entry) => entry.date === now.date);
  const events = eventsInTown(day);
  get("today").replaceChildren(events.length ? eventList(events) : element("p",
    day ? "Pre zvolenú obec dnes nie je uvedený termín."
      : active ? "Dnešný deň nemá v rozpise samostatný riadok." : "Poriadok na dnešný deň zatiaľ nemáme."
  ));

  const upcoming = schedules.flatMap((item) => item.days
    .filter((entry) => entry.date >= now.date && scheduleOn(entry.date) === item)
    .flatMap((entry) => eventsInTown(entry).map((event) => ({ ...event, date: entry.date }))))
    .filter((event) => event.date > now.date || event.time >= now.time)
    .sort((a, b) => (a.date + a.time).localeCompare(b.date + b.time));

  const next = get("next");
  if (upcoming.length) {
    const first = upcoming[0];
    next.replaceChildren(element("p", format(fullDate, first.date), "detail"),
      eventList(upcoming.filter((event) => event.date === first.date && event.time === first.time)));
  } else {
    next.replaceChildren(element("p", "Ďalší termín zatiaľ nemáme."));
  }
}

function render() {
  const now = localClock();
  const active = scheduleOn(now.date);
  const selected = schedules.find((item) => item.source === periodFilter.value) ?? active;
  renderSummary(now, active);
  const target = get("schedule");
  target.replaceChildren();
  if (!selected) {
    target.append(element("p", "Aktuálny poriadok zatiaľ nemáme. Tu sa zobrazí po načítaní z farskej stránky.", "notice"));
    return;
  }

  for (const day of selected.days) {
    const events = eventsInTown(day);
    if (townFilter.value && !events.length) continue;
    const card = element("article", "", day.date === now.date ? "day current" : "day");
    const caption = element("div");
    caption.append(element("h3", format(fullDate, day.date)), element("p", day.feast, "detail"));
    const details = element("div");
    details.append(events.length ? eventList(events) : element("p", "Čas nie je uvedený.", "detail"));
    if (day.notes.length) {
      const notes = element("ul", "", "notes");
      for (const note of day.notes) notes.append(element("li", note));
      details.append(notes);
    }
    card.append(caption, details);
    target.append(card);
  }

  if (!target.childElementCount) {
    target.append(element("p", "Vo vybranom poriadku sa nenašiel termín pre túto obec.", "notice"));
  }
  const source = element("a", "Otvoriť pôvodný farský poriadok");
  source.href = selected.source;
  target.append(source);
}

async function init() {
  try {
    const response = await fetch("./poriadky.json");
    if (!response.ok) throw new Error(String(response.status));
    ({ schedules } = await response.json());
    for (const item of schedules) {
      const label = format(shortDate, item.start) + " – " + format(shortDate, item.end);
      periodFilter.add(new Option(label, item.source));
    }
    townFilter.addEventListener("change", render);
    periodFilter.addEventListener("change", render);
    render();
    setInterval(render, 60_000);
  } catch (error) {
    get("today").textContent = "Rozpis sa nepodarilo načítať.";
    get("next").textContent = "Údaje sú dočasne nedostupné.";
    get("schedule").append(element("p", "Skúste obnoviť stránku alebo otvorte farský originál nižšie.", "notice"));
    console.error(error);
  }
}

init();
