import { useEffect, useState } from 'react'

/**
 * 极简 hash 路由。
 *
 * 为什么不用 react-router：上线形态（A2 = (b)）是把产物丢进 LightRAG 容器的
 * 静态目录，由 Starlette 的 StaticFiles 提供 —— 它**没有 SPA fallback**，
 * 任何 `/chapters` 这样的真实路径刷新都会 404。hash 路由天然免疫这个问题，
 * 也让包体少一个依赖。
 *
 * 约定：#/  #/chapters  #/about，查询参数写在 hash 里（#/?q=…&preset=…）。
 */
export interface Route {
  name: 'home' | 'chapters' | 'about'
  query: URLSearchParams
}

function parse(hash: string): Route {
  const raw = hash.replace(/^#/, '') || '/'
  const [path, qs = ''] = raw.split('?')
  const query = new URLSearchParams(qs)
  const clean = path.replace(/\/+$/, '') || '/'
  if (clean === '/chapters') return { name: 'chapters', query }
  if (clean === '/about') return { name: 'about', query }
  return { name: 'home', query }
}

export function useHashRoute(): Route {
  const [route, setRoute] = useState<Route>(() => parse(window.location.hash))
  useEffect(() => {
    const onChange = () => setRoute(parse(window.location.hash))
    window.addEventListener('hashchange', onChange)
    return () => window.removeEventListener('hashchange', onChange)
  }, [])
  return route
}

export function navigate(to: string): void {
  window.location.hash = to.startsWith('#') ? to : `#${to}`
}
