import React, {useEffect, useState} from "react"
import {createRoot} from "react-dom/client"
import {api} from "./api"
import {Editor, SignIn} from "./Forms"
import {TripList, TripPage} from "./Planner"
import "./style.css"

function App() {
  const [user,setUser] = useState(undefined)
  const [hash,setHash] = useState(location.hash)
  const [data,setData] = useState(null)
  const [version,reload] = useState(0)
  const [form,setForm] = useState(null)
  const [error,setError] = useState("")
  const [busy,setBusy] = useState(false)
  const route = hash.match(/^#\/trip\/(\d+)(?:\/(schedule|budget|packing))?$/)
  const id = route?.[1]
  const tab = route?.[2] || "schedule"
  function reset() { setUser(null); setData(null); setForm(null); setError(""); location.hash="/" }
  function loadUser() {
    setError("")
    api("/auth/me").then(setUser).catch(err=>{if(err.status===401) setUser(null); else setError(err.message)})
  }
  useEffect(()=>{
    loadUser()
    const navigate = ()=>{setHash(location.hash); setForm(null); setError("")}
    window.addEventListener("hashchange",navigate)
    window.addEventListener("session-ended",reset)
    return ()=>{window.removeEventListener("hashchange",navigate); window.removeEventListener("session-ended",reset)}
  },[])
  useEffect(()=>{
    if(!user) return
    let active=true
    setData(null); setError("")
    api(id ? "/trips/"+id : "/trips").then(result=>{if(active) setData(result)})
      .catch(err=>{if(active) setError(err.message)})
    return ()=>{active=false}
  },[user,id,version])
  function saved(destination) {
    setForm(null)
    if(destination) location.hash=destination
    reload(n=>n+1)
  }
  async function toggle(item) {
    setBusy(true); setError("")
    try {await api("/trips/"+id+"/items/"+item.id,"PUT",{name:item.name,is_packed:!item.is_packed}); saved()}
    catch(err){setError(err.message)}
    finally{setBusy(false)}
  }
  async function logout(){
    try {await api("/auth/logout","POST"); reset()} catch(err){setError(err.message)}
  }
  const edit = (kind,row,remove=false)=>setForm({kind,row,remove})
  const ready = id ? data?.id===Number(id) : Array.isArray(data)
  return <><header><div className="bar"><a className="brand" href="#/"><i aria-hidden="true">↗</i>TravelPlanner</a>
    {user && <div className="account"><span>{user.email}</span><button onClick={logout}>Выйти</button></div>}</div></header>
    {user===null ? <SignIn onLogin={setUser}/> : <main className="workspace">
    {error && <div className="notice" role="alert">{error} <button onClick={()=>user ? reload(n=>n+1) : loadUser()}>Повторить</button> {id && <a href="#/">К поездкам</a>}</div>}
    {!ready && !error && <p role="status">Загрузка…</p>}
    {ready && (id ? <TripPage trip={data} tab={tab} edit={edit} toggle={toggle} busy={busy}/> : <TripList trips={data} edit={edit}/>)}</main>}
    {form && <Editor form={form} trip={id ? data : null} close={()=>setForm(null)} saved={saved}/>}</>
}
createRoot(document.getElementById("root")).render(<App/>)
