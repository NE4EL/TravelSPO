import React, {useEffect, useRef, useState} from "react"
import {api} from "./api"

export function SignIn({onLogin}) {
  const [register, setRegister] = useState(false)
  const [error, setError] = useState("")
  const [busy, setBusy] = useState(false)
  async function submit(e) {
    e.preventDefault()
    const values = Object.fromEntries(new FormData(e.currentTarget))
    setBusy(true); setError("")
    try { onLogin(await api("/auth/" + (register ? "register" : "login"), "POST", values)) }
    catch (err) { setError(err.message) }
    finally { setBusy(false) }
  }
  return <main className="entry"><section className="intro"><div className="route-art" aria-hidden="true">↗</div>
    <h1>Планировщик<br/>путешествий<span>.</span></h1><p>Расписание, бюджет и список вещей для каждой поездки.</p></section>
    <section className="auth card"><h2>{register ? "Создать аккаунт" : "Вход в аккаунт"}</h2>
    <form onSubmit={submit}><label>Email<input type="email" name="email" autoComplete="email" required maxLength="255"/></label>
    <label>Пароль<input type="password" key={register} name="password" autoComplete={register ? "new-password" : "current-password"} minLength="8" maxLength="128" required/></label>
    {register && <small>От 8 до 128 символов</small>}{error && <p role="alert">{error}</p>}
    <button className="primary" disabled={busy}>{register ? "Зарегистрироваться" : "Войти"}</button></form>
    <button className="link" disabled={busy} onClick={()=>{setError(""); setRegister(!register)}}>{register ? "Уже есть аккаунт? Войти" : "Создать аккаунт"}</button></section></main>
}

function Field({label, name, initial, ...props}) {
  return <label>{label}<input name={name} defaultValue={initial ?? ""} {...props}/></label>
}

const titles = {trips:["Новая поездка","Изменить поездку"], activities:["Новое мероприятие","Изменить мероприятие"],
  expenses:["Новый расход","Изменить расход"], items:["Добавить вещь","Изменить вещь"]}

// HTML time inputs support milliseconds; keep finer API precision if unchanged.
const timeValue = value => value?.slice(0,12) || ""

export function Editor({form, trip, close, saved}) {
  const {kind, row = {}, remove} = form
  const dialog = useRef(null)
  const [busy,setBusy] = useState(false)
  const [error,setError] = useState("")
  useEffect(()=>{const el = dialog.current; el.showModal(); return ()=>el.close()}, [])
  async function submit(e) {
    e.preventDefault()
    const values = Object.fromEntries(new FormData(e.currentTarget))
    if (kind === "activities") {
      for (const name of ["starts_at", "ends_at"]) {
        values[name] = values[name] === timeValue(row[name]) ? row[name] || null : values[name] || null
      }
    }
    if (kind === "expenses") values.activity_id = values.activity_id ? Number(values.activity_id) : null
    if (kind === "items") values.is_packed = row.is_packed || false
    let path = kind === "trips" ? "/trips" : "/trips/" + trip.id + "/" + kind
    if (row.id) path += "/" + row.id
    setBusy(true); setError("")
    try {
      const result = await api(path, remove ? "DELETE" : row.id ? "PUT" : "POST", remove ? undefined : values)
      saved(kind === "trips" ? (remove ? "#/" : "#/trip/" + (row.id || result.id)) : null)
    } catch(err) {setError(err.message); setBusy(false)}
  }
  return <dialog ref={dialog} aria-labelledby="form-title" onCancel={e=>{e.preventDefault(); if(!busy) close()}}>
    <h2 id="form-title">{remove ? "Подтвердите удаление" : titles[kind][row.id ? 1 : 0]}</h2>
    <form onSubmit={submit}>
    {remove ? <p>Удалить «{row.title || row.name}»{kind === "trips" ? " вместе с расписанием, расходами и вещами" : ""}?</p> : <>
      <Field label={kind === "items" ? "Название вещи" : "Название"} name={kind === "items" ? "name" : "title"} initial={row.title || row.name} required maxLength="120"/>
      {kind === "trips" && <>
        <Field label="Направление" name="destination" initial={row.destination} required maxLength="120"/>
        <div className="pair"><Field type="date" label="Начало поездки" name="start_date" initial={row.start_date} required/>
        <Field type="date" label="Конец поездки" name="end_date" initial={row.end_date} required/></div>
        <Field type="number" label="Бюджет, ₽" name="budget_limit" initial={row.budget_limit ?? 0} min="0" max="9999999999.99" step=".01" required/></>}
      {kind === "activities" && <>
        <Field type="date" label="Дата мероприятия" name="activity_date" initial={row.activity_date || trip.start_date} min={trip.start_date} max={trip.end_date} required/>
        <div className="pair"><Field type="time" step="any" label="Начало" name="starts_at" initial={timeValue(row.starts_at)}/>
        <Field type="time" step="any" label="Окончание" name="ends_at" initial={timeValue(row.ends_at)}/></div>
        <label>Место или описание<textarea name="description" defaultValue={row.description} maxLength="2000"/></label></>}
      {kind === "expenses" && <>
        <Field type="number" label="Сумма, ₽" name="amount" min=".01" max="9999999999.99" step=".01" initial={row.amount} required/>
        <label>Мероприятие<select name="activity_id" defaultValue={row.activity_id || ""}><option value="">Без привязки</option>
        {trip.activities.map(a=><option key={a.id} value={a.id}>{a.activity_date} · {a.title}</option>)}</select></label></>}
    </>}
    {error && <p role="alert">{error}</p>}
    <div className="buttons"><button type="button" onClick={close} disabled={busy}>Отмена</button>
    <button className={remove ? "danger" : "primary"} disabled={busy}>{remove ? "Удалить" : "Сохранить"}</button></div></form></dialog>
}
