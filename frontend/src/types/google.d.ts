// Google Identity Services(index.html의 accounts.google.com/gsi/client)에서 쓰는 만큼만 선언한다.
// https://developers.google.com/identity/gsi/web/reference/js-reference

type GoogleCredentialResponse = { credential: string }

type GoogleButtonOptions = {
  theme?: 'outline' | 'filled_blue' | 'filled_black'
  size?: 'large' | 'medium' | 'small'
  shape?: 'rectangular' | 'pill' | 'circle' | 'square'
  text?: 'signin_with' | 'signup_with' | 'continue_with' | 'signin'
  logo_alignment?: 'left' | 'center'
  locale?: string
  width?: number
}

interface Window {
  google?: {
    accounts: {
      id: {
        initialize(options: { client_id: string; callback: (res: GoogleCredentialResponse) => void }): void
        renderButton(parent: HTMLElement, options: GoogleButtonOptions): void
      }
    }
  }
}
