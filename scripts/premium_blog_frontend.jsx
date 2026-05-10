import { useEffect, useMemo, useState } from 'react'
import { motion } from 'framer-motion'

function SearchIcon(props){return <svg viewBox='0 0 24 24' fill='none' stroke='currentColor' strokeWidth='2' {...props}><circle cx='11' cy='11' r='7'/><path d='M20 20l-3.5-3.5'/></svg>}
function EyeIcon(props){return <svg viewBox='0 0 24 24' fill='none' stroke='currentColor' strokeWidth='2' {...props}><path d='M2 12s4-6 10-6 10 6 10 6-4 6-10 6S2 12 2 12z'/><circle cx='12' cy='12' r='3'/></svg>}
function ArrowRightIcon(props){return <svg viewBox='0 0 24 24' fill='none' stroke='currentColor' strokeWidth='2' {...props}><path d='M5 12h14'/><path d='M13 5l7 7-7 7'/></svg>}
function SunIcon(props){return <svg viewBox='0 0 24 24' fill='none' stroke='currentColor' strokeWidth='2' {...props}><circle cx='12' cy='12' r='4'/></svg>}
function MoonIcon(props){return <svg viewBox='0 0 24 24' fill='none' stroke='currentColor' strokeWidth='2' {...props}><path d='M21 12.8A9 9 0 1 1 11.2 3 7 7 0 0 0 21 12.8z'/></svg>}

function AICover({title,tag,isDark}){
const tones={Security:'from-cyan-500/20',HTB:'from-emerald-500/20',Kubernetes:'from-sky-500/20',Design:'from-violet-500/20',Tech:'from-indigo-500/20',CTF:'from-rose-500/20'}
const tone=tones[tag]||'from-zinc-500/20'
return <div className={isDark?'h-48 rounded-2xl border border-zinc-800 bg-zinc-950 relative overflow-hidden':'h-48 rounded-2xl border border-zinc-200 bg-white relative overflow-hidden'}>
<div className={`absolute inset-0 bg-gradient-to-br ${tone} to-transparent`}></div>
<div className='absolute inset-0 opacity-20 bg-[linear-gradient(rgba(255,255,255,0.12)_1px,transparent_1px),linear-gradient(90deg,rgba(255,255,255,0.12)_1px,transparent_1px)] bg-[size:22px_22px]'></div>
<div className='absolute top-4 left-4 text-[10px] uppercase tracking-[0.3em] text-zinc-400'>AI Cover</div>
<div className='absolute left-5 right-5 bottom-5'><div className='text-xs text-zinc-400 uppercase tracking-[0.25em]'>{tag}</div><h3 className='mt-2 text-xl font-semibold leading-tight'>{title}</h3></div>
</div>}

export default function PremiumBlog(){
const posts=[
{id:1,tag:'HTB',title:'SteamCloud Writeup',desc:'Kubernetes privilege escalation walkthrough.',views:1284},
{id:2,tag:'Security',title:'Zero Trust Notes',desc:'Modern defensive mindset.',views:942},
{id:3,tag:'Kubernetes',title:'Container Escape Basics',desc:'Understand hostPath risk.',views:1880},
{id:4,tag:'CTF',title:'Web Challenge Tricks',desc:'Common bypass patterns.',views:731},
{id:5,tag:'Tech',title:'Build Tools with Python',desc:'CLI automation workflow.',views:563},
{id:6,tag:'Design',title:'Minimal Premium UI',desc:'High-end interfaces through restraint.',views:1102}
]
const tags=['All',...new Set(posts.map(p=>p.tag))]
const [theme,setTheme]=useState('dark')
const [query,setQuery]=useState('')
const [activeTag,setActiveTag]=useState('All')
const [selected,setSelected]=useState(null)
const [progress,setProgress]=useState(0)
const [likes,setLikes]=useState({})
useEffect(()=>{const t=localStorage.getItem('theme');if(t)setTheme(t)},[])
useEffect(()=>localStorage.setItem('theme',theme),[theme])
useEffect(()=>{const onScroll=()=>{const h=document.documentElement;const total=h.scrollHeight-h.clientHeight;setProgress(total>0?(window.scrollY/total)*100:0)};window.addEventListener('scroll',onScroll);onScroll();return ()=>window.removeEventListener('scroll',onScroll)},[])
const isDark=theme==='dark'
const ui={page:isDark?'min-h-screen bg-black text-white':'min-h-screen bg-white text-zinc-900',muted:isDark?'text-zinc-400':'text-zinc-600',header:isDark?'sticky top-0 z-50 bg-black/75 border-b border-zinc-900 backdrop-blur-xl':'sticky top-0 z-50 bg-white/80 border-b border-zinc-200 backdrop-blur-xl',input:isDark?'w-full pl-11 pr-4 py-4 rounded-2xl border border-zinc-900 bg-zinc-950':'w-full pl-11 pr-4 py-4 rounded-2xl border border-zinc-200 bg-white',card:isDark?'rounded-3xl border border-zinc-900 bg-zinc-950 hover:border-zinc-700':'rounded-3xl border border-zinc-200 bg-white hover:shadow-xl'}
const filtered=useMemo(()=>posts.filter(p=>(activeTag==='All'||p.tag===activeTag)&&(`${p.title} ${p.desc}`.toLowerCase().includes(query.toLowerCase()))),[query,activeTag])
const current=posts.find(p=>p.id===selected)

if (current) {
  return (
    <div className={ui.page}>
      <div className='fixed top-0 left-0 h-1 bg-cyan-500 z-[60]' style={{ width: `${progress}%` }} />
      <header className={ui.header}>
        <div className='max-w-5xl mx-auto px-6 py-4 flex justify-between items-center'>
          <button onClick={() => setSelected(null)} className={ui.muted}>← Back</button>
          <div className='font-semibold text-xl'>Aether Journal</div>
          <button onClick={() => setTheme(isDark ? 'light' : 'dark')} className='px-4 py-2 rounded-xl border border-zinc-300/20'>Toggle</button>
        </div>
      </header>
      <main className='max-w-4xl mx-auto px-6 py-14'>
        <AICover title={current.title} tag={current.tag} isDark={isDark} />
        <h1 className='mt-8 text-5xl md:text-7xl font-semibold tracking-tight'>{current.title}</h1>
        <p className={`mt-4 text-2xl ${ui.muted}`}>{current.desc}</p>
        <div className='grid lg:grid-cols-[220px_1fr] gap-10 mt-12'>
          <aside className='hidden lg:block'>
            <div className={isDark ? 'rounded-2xl border border-zinc-800 bg-zinc-950 p-5' : 'rounded-2xl border border-zinc-200 bg-zinc-50 p-5'}>
              <div className='text-xs uppercase tracking-[0.3em] text-zinc-500'>Contents</div>
              <ul className='mt-4 space-y-3 text-sm'><li>Overview</li><li>Key Ideas</li><li>Example</li><li>Takeaway</li></ul>
            </div>
          </aside>
          <article className={`space-y-8 text-lg leading-9 ${ui.muted}`}>
            <section><h2 className='text-2xl font-semibold mb-3'>Overview</h2><p>Clear sections, practical examples, concise takeaways.</p></section>
            <section><h2 className='text-2xl font-semibold mb-3'>Example</h2><div className={isDark ? 'rounded-2xl border border-zinc-800 bg-zinc-950 p-5 font-mono text-sm whitespace-pre-wrap' : 'rounded-2xl border border-zinc-200 bg-zinc-50 p-5 font-mono text-sm whitespace-pre-wrap'}>{`kubectl get pods -A
python3 scanner.py --target example.com`}</div></section>
            <section className='pt-6 flex gap-3'>
              <button onClick={() => setLikes(v => ({ ...v, [current.id]: (v[current.id] || 0) + 1 }))} className='px-4 py-2 rounded-xl border border-zinc-300/20'>👍 Like {likes[current.id] || 0}</button>
              <button className='px-4 py-2 rounded-xl border border-zinc-300/20'>Share</button>
            </section>
          </article>
        </div>
      </main>
    </div>
  )
}

return <div className={ui.page}><header className={ui.header}><div className='max-w-6xl mx-auto px-6 py-4 flex justify-between items-center'><div className='font-semibold text-xl'>Aether Journal</div><button onClick={()=>setTheme(isDark?'light':'dark')} className='px-4 py-2 rounded-xl border border-zinc-300/20'>{isDark?<span className='flex gap-2 items-center'><SunIcon className='w-4 h-4'/>Light</span>:<span className='flex gap-2 items-center'><MoonIcon className='w-4 h-4'/>Dark</span>}</button></div></header>
<section className='max-w-6xl mx-auto px-6 pt-20 pb-10'><h1 className='text-6xl md:text-8xl font-semibold tracking-tight'>V5 Production Blog</h1><p className={`mt-5 text-xl max-w-2xl ${ui.muted}`}>AI cover system, tag categories, reading stats, premium layout.</p><div className='max-w-xl mt-8 relative'><SearchIcon className='absolute left-4 top-4 w-5 h-5 text-zinc-500'/><input className={ui.input} placeholder='Search articles...' value={query} onChange={e=>setQuery(e.target.value)} /></div><div className='flex flex-wrap gap-3 mt-8'>{tags.map(tag=><button key={tag} onClick={()=>setActiveTag(tag)} className={(activeTag===tag?'bg-zinc-800 text-white ':'') + (isDark?'px-4 py-2 rounded-xl border border-zinc-800':'px-4 py-2 rounded-xl border border-zinc-200')}>{tag}</button>)}</div></section>
<section className='max-w-6xl mx-auto px-6 grid lg:grid-cols-3 gap-6 pb-24'>{filtered.map((post,i)=><motion.article key={post.id} initial={{opacity:0,y:20}} animate={{opacity:1,y:0}} transition={{delay:i*0.04}} whileHover={{y:-4}} className={`${ui.card} p-6 cursor-pointer`} onClick={()=>setSelected(post.id)}><AICover title={post.title} tag={post.tag} isDark={isDark}/><div className='mt-5 flex items-center justify-between'><span className='text-xs uppercase tracking-[0.3em] text-zinc-500'>{post.tag}</span><span className={`text-sm flex items-center gap-1 ${ui.muted}`}><EyeIcon className='w-4 h-4'/>{post.views.toLocaleString()}</span></div><h3 className='mt-3 text-3xl font-semibold tracking-tight'>{post.title}</h3><p className={`mt-3 ${ui.muted}`}>{post.desc}</p><div className='mt-6 flex items-center gap-2 font-medium'>Read <ArrowRightIcon className='w-4 h-4'/></div></motion.article>)} </section><footer className={isDark?'border-t border-zinc-900 py-10 text-center text-sm text-zinc-500':'border-t border-zinc-200 py-10 text-center text-sm text-zinc-500'}>© 2026 Aether Journal — V6 Content System</footer></div>
}
