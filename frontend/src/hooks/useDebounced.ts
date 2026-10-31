import { useEffect, useState } from 'react'

/** Returns `value` once it has stopped changing for `delay` milliseconds. */
export function useDebounced<T>(value: T, delay = 350): T {
  const [settled, setSettled] = useState(value)
  useEffect(() => {
    const timer = setTimeout(() => setSettled(value), delay)
    return () => clearTimeout(timer)
  }, [value, delay])
  return settled
}
