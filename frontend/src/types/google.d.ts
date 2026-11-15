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

// 구글 캘린더 권한 팝업(oauth2.initCodeClient). 받은 code는 서버가 토큰으로 바꾼다
// https://developers.google.com/identity/oauth2/web/reference/js-reference
type GoogleCodeResponse = { code?: string; error?: string }
type GoogleCodeClientOptions = {
  client_id: string
  scope: string
  ux_mode: 'popup'
  access_type?: 'offline'
  prompt?: 'consent'
  callback: (res: GoogleCodeResponse) => void
  error_callback?: (err: { type: string }) => void // 팝업을 닫았거나 못 열었을 때
}

interface Window {
  google?: {
    accounts: {
      id: {
        initialize(options: { client_id: string; callback: (res: GoogleCredentialResponse) => void }): void
        renderButton(parent: HTMLElement, options: GoogleButtonOptions): void
      }
      oauth2: {
        initCodeClient(options: GoogleCodeClientOptions): { requestCode(): void }
      }
    }
  }
}
