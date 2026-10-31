/** Joins class names, skipping empty ones. */
export function cx(...classes: (string | false | null | undefined)[]): string {
  return classes.filter(Boolean).join(' ')
}

export function formatDateTime(iso: string): string {
  return new Date(iso).toLocaleString('en-GB', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })
}

/** Human wording for audit action codes. Unknown codes are shown as they are. */
export const ACTION_LABELS: Record<string, string> = {
  'auth.login': 'Signed in',
  'auth.logout': 'Signed out',
  'auth.login_failed': 'Failed sign-in',
  'user.created': 'Created a user',
  'user.updated': 'Updated a user',
  'barcode.generated': 'Generated a barcode',
  'barcode.batch_generated': 'Ran a barcode batch',
  'barcode.refused': 'Refused an identity layout',
}

export function actionLabel(code: string): string {
  return ACTION_LABELS[code] ?? code
}
