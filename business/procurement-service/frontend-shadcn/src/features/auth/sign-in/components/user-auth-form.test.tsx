import { beforeEach, describe, expect, it, vi } from 'vitest'
import { render, type RenderResult } from 'vitest-browser-react'
import { type Locator, userEvent } from 'vitest/browser'
import { UserAuthForm } from './user-auth-form'

const FORM_MESSAGES = {
  emailEmpty: 'Please enter your email.',
  passwordEmpty: 'Please enter your password.',
  passwordShort: 'Password must be at least 7 characters long.',
} as const

const navigate = vi.fn()
const setUserMock = vi.fn()

vi.mock('@/stores/auth-store', () => ({
  useAuthStore: () => ({
    auth: {
      setUser: setUserMock,
    },
  }),
}))

vi.mock('@tanstack/react-router', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@tanstack/react-router')>()
  return {
    ...actual,
    useNavigate: () => navigate,
    Link: ({
      children,
      to,
      className,
      ...rest
    }: {
      children?: React.ReactNode
      to: string
      className?: string
    }) => (
      <a href={to} className={className} {...rest}>
        {children}
      </a>
    ),
  }
})

// Mock the global fetch for Gateway API calls
const mockFetch = vi.fn()

beforeEach(() => {
  vi.stubGlobal('fetch', mockFetch)
  mockFetch.mockReset()
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('UserAuthForm', () => {
  describe('Rendering without redirectTo', () => {
    let screen: RenderResult
    let emailInput: Locator
    let passwordInput: Locator
    let signInButton: Locator
    let forgotPasswordLink: Locator

    beforeEach(async () => {
      vi.clearAllMocks()
      screen = await render(<UserAuthForm />)
      emailInput = screen.getByRole('textbox', { name: /^Email$/i })
      passwordInput = screen.getByLabelText(/^Password$/i)
      signInButton = screen.getByRole('button', { name: /^Sign in$/i })
      forgotPasswordLink = screen.getByText(/^Forgot password\?$/i)
    })

    it('renders fields, submit button, and forgot password link', async () => {
      await expect.element(emailInput).toBeInTheDocument()
      await expect.element(passwordInput).toBeInTheDocument()
      await expect.element(signInButton).toBeInTheDocument()
      await expect.element(forgotPasswordLink).toBeInTheDocument()
    })

    it('shows validation messages when submitting empty form', async () => {
      await userEvent.click(signInButton)

      await expect
        .element(screen.getByText(FORM_MESSAGES.emailEmpty))
        .toBeInTheDocument()
      await expect
        .element(screen.getByText(FORM_MESSAGES.passwordEmpty))
        .toBeInTheDocument()
    })

    it('authenticates with Gateway and navigates on success', async () => {
      // Mock Gateway login response
      mockFetch
        .mockResolvedValueOnce({
          ok: true,
          json: () => Promise.resolve({ expires_in: 86400, needs_setup: false }),
        })
        // Mock Gateway /me response
        .mockResolvedValueOnce({
          ok: true,
          json: () => Promise.resolve({ id: 'user-1', email: 'a@b.com', system_role: 'user' }),
        })

      await userEvent.fill(emailInput, 'a@b.com')
      await userEvent.fill(passwordInput, '1234567')
      await userEvent.click(signInButton)

      await vi.waitFor(() => expect(setUserMock).toHaveBeenCalledOnce())
      expect(setUserMock).toHaveBeenCalledWith(
        expect.objectContaining({
          email: 'a@b.com',
          accountNo: expect.any(String),
          role: expect.any(Array),
          exp: expect.any(Number),
        })
      )

      await vi.waitFor(() =>
        expect(navigate).toHaveBeenCalledWith({ to: '/', replace: true })
      )
    })

    it('shows error message on login failure', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: false,
        json: () => Promise.resolve({ detail: 'Incorrect email or password' }),
      })

      await userEvent.fill(emailInput, 'bad@b.com')
      await userEvent.fill(passwordInput, '1234567')
      await userEvent.click(signInButton)

      await vi.waitFor(() =>
        expect(screen.getByText('Incorrect email or password')).toBeTruthy()
      )
    })
  })

  it('navigates to redirectTo when provided', async () => {
    vi.clearAllMocks()

    mockFetch
      .mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({ expires_in: 86400 }),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({ id: 'user-1', email: 'a@b.com', system_role: 'user' }),
      })

    const { getByRole, getByLabelText } = await render(
      <UserAuthForm redirectTo='/settings' />
    )

    await userEvent.fill(getByRole('textbox', { name: /Email/i }), 'a@b.com')
    await userEvent.fill(getByLabelText('Password'), '1234567')
    await userEvent.click(getByRole('button', { name: /Sign in/i }))

    await vi.waitFor(() => expect(setUserMock).toHaveBeenCalledOnce())

    await vi.waitFor(() =>
      expect(navigate).toHaveBeenCalledWith({
        to: '/settings',
        replace: true,
      })
    )
  })
})
