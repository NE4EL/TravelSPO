import React from "react"
import {date, money} from "./api"

export function TripList({trips,edit}) {
  return <><div className="heading"><h1>Мои поездки<span>.</span></h1><button className="primary" onClick={()=>edit("trips")}>+ Новая поездка</button></div>
    {trips.length === 0 && <div className="empty"><h2>Первая поездка</h2><p>Укажите направление и даты, чтобы начать планирование.</p></div>}
    <div className="grid">{trips.map(trip=><a className="ticket" key={trip.id} href={"#/trip/"+trip.id}>
      <div className="destination">{trip.destination}<span aria-hidden="true">↗</span></div>
      <h2>{trip.title}</h2><div className="dates">{date(trip.start_date)} — {date(trip.end_date)}</div></a>)}</div></>
}

const tabs = {schedule:"Расписание",budget:"Бюджет",packing:"Вещи"}
function Actions({kind,row,edit}) {
  return <div className="actions"><button onClick={()=>edit(kind,row)} aria-label={"Изменить: "+(row.title || row.name)}>Изменить</button>
    <button onClick={()=>edit(kind,row,true)} aria-label={"Удалить: "+(row.title || row.name)}>Удалить</button></div>
}
function Section({title,action,add,children}) {
  return <section className="card panel"><div className="heading"><h2>{title}</h2><button onClick={add}>{action}</button></div>{children}</section>
}

export function TripPage({trip,tab,edit,toggle,busy}) {
  const {activities,expenses,packing_items:items} = trip
  const groups = new Map()
  for (const entry of activities) {
    if (!groups.has(entry.activity_date)) groups.set(entry.activity_date,[])
    groups.get(entry.activity_date).push(entry)
  }
  return <><a className="back" href="#/">← Мои поездки</a><div className="heading"><div><p className="destination">{trip.destination}</p>
    <h1>{trip.title}<span>.</span></h1><p>{date(trip.start_date)} — {date(trip.end_date)}</p></div><Actions kind="trips" row={trip} edit={edit}/></div>
    <div className="metrics"><div><small>Бюджет</small><strong>{money(trip.budget_limit)}</strong></div>
    <div><small>Расходы</small><strong>{money(trip.total)}</strong></div><div><small>Остаток</small><strong>{money(trip.remaining)}</strong></div>
    <div><small>Собрано вещей</small><strong>{items.filter(i=>i.is_packed).length} / {items.length}</strong></div></div>
    <nav className="tabs" aria-label="Разделы поездки">{Object.entries(tabs).map(([key,label])=><a key={key}
      aria-current={tab===key ? "page" : undefined} href={"#/trip/"+trip.id+"/"+key}>{label}</a>)}</nav>
    {tab==="schedule" && <Section title="Расписание по дням" action="+ Мероприятие" add={()=>edit("activities")}>
      {!activities.length && <p>Мероприятий пока нет.</p>}
      {[...groups].map(([day,entries])=><section key={day}><h3>{date(day)}</h3>{entries.map(a=><div className="row" key={a.id}>
        <time>{a.starts_at?.slice(0,5) || "Без времени"}{a.ends_at && " – "+a.ends_at.slice(0,5)}</time>
        <div className="grow"><b>{a.title}</b>{a.description && <p>{a.description}</p>}</div><Actions kind="activities" row={a} edit={edit}/></div>)}</section>)}</Section>}
    {tab==="budget" && <Section title="Планируемые расходы" action="+ Расход" add={()=>edit("expenses")}>
      {!expenses.length && <p>Расходов пока нет.</p>}
      {expenses.map(e=><div className="row" key={e.id}><div className="grow"><b>{e.title}</b>
      {e.activity_id && <p>{activities.find(a=>a.id===e.activity_id)?.title}</p>}</div><strong>{money(e.amount)}</strong><Actions kind="expenses" row={e} edit={edit}/></div>)}</Section>}
    {tab==="packing" && <Section title="Список вещей" action="+ Вещь" add={()=>edit("items")}>
      {!items.length && <p>Список пока пуст.</p>}{items.map(i=><div className="row" key={i.id}><label className="check grow">
      <input type="checkbox" checked={i.is_packed} disabled={busy} onChange={()=>toggle(i)}/><span>{i.name}</span></label><Actions kind="items" row={i} edit={edit}/></div>)}</Section>}
  </>
}
