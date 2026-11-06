import { useCallback, useEffect, useRef, useState } from 'react'

// 轻量取数 hook：loading / error / data / reload；卸载或依赖变化时取消旧请求。
export function useAsync(fn, deps) {
  const [state, setState] = useState({ loading: true, error: null, data: null })
  const seq = useRef(0)
  const fnRef = useRef(fn)
  fnRef.current = fn

  const run = useCallback(() => {
    const id = ++seq.current
    const ctrl = new AbortController()
    setState((s) => ({ ...s, loading: true, error: null }))
    fnRef.current(ctrl.signal).then(
      (data) => {
        if (id === seq.current) setState({ loading: false, error: null, data })
      },
      (error) => {
        if (error?.name === 'AbortError') return
        if (id === seq.current) setState((s) => ({ loading: false, error, data: s.data }))
      },
    )
    return () => ctrl.abort()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps)

  useEffect(() => run(), [run])
  return { ...state, reload: run }
}
