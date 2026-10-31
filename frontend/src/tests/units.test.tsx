import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { messageFrom } from '../api/client'
import { Figure } from '../components/ui'
import { visibleNavigation } from '../navigation'

const labels = (role: Parameters<typeof visibleNavigation>[0]) =>
  visibleNavigation(role).flatMap((g) => g.items.map((i) => i.label))

describe('navigation', () => {
  it('shows all ten sections to administrators', () => {
    expect(labels('ADMINISTRATOR')).toHaveLength(10)
  })

  it('hides administration pages from other roles', () => {
    for (const role of ['ANALYST', 'REVIEWER', 'DEVELOPER', 'READ_ONLY'] as const) {
      const items = labels(role)
      expect(items).not.toContain('Audit Logs')
      expect(items).not.toContain('User Management')
      expect(items).toContain('Settings')
    }
  })
})

describe('Figure', () => {
  it('shows the number when there is one', () => {
    render(<Figure label="Sign-ins" value={1234} />)
    expect(screen.getByText('1,234')).toBeInTheDocument()
  })

  it('says "not available" instead of showing 0 for unbuilt modules', () => {
    render(<Figure label="Barcodes generated" value={null} note="Arrives with the Barcode Generator" />)
    expect(screen.getByText('Arrives with the Barcode Generator')).toBeInTheDocument()
    expect(screen.queryByText('0')).not.toBeInTheDocument()
  })
})

describe('messageFrom', () => {
  it('uses the detail message', () => {
    expect(messageFrom({ detail: 'Invalid username or password.' }, 'x')).toBe('Invalid username or password.')
  })

  it('names the field for field errors', () => {
    expect(messageFrom({ password: ['This password is too short.'] }, 'x')).toBe('password: This password is too short.')
  })

  it('falls back when the body is empty', () => {
    expect(messageFrom(null, 'Fallback')).toBe('Fallback')
  })
})
