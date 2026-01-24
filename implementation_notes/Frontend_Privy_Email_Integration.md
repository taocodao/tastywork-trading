# Frontend Integration Notes

## Signal Approval with User Email

When a user approves a signal via the `/api/signals/{id}/approve` endpoint, the frontend must now include the user's email address from their Privy account.

### Required Changes

**Before:**
```javascript
const response = await fetch(`/api/signals/${signalId}/approve`, {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    userId: user.id,  // From Privy
    refreshToken: oauthTokens.refresh_token,
    accountNumber: tastytrade.accountNumber
  })
});
```

**After:**
```javascript
import { usePrivy } from '@privy-io/react-auth';

const { user } = usePrivy();

const response = await fetch(`/api/signals/${signalId}/approve`, {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    userId: user.id,           // From Privy
    userEmail: user.email?.address,  // NEW: User's email from Privy
    refreshToken: oauthTokens.refresh_token,
    accountNumber: tastytrade.accountNumber
  })
});
```

### Why This Change?

The position tracking system now stores the user's email to send exit alerts when risk rules trigger:
- **Profit target** reached (25% of entry debit)
- **Stop loss** hit (50% of entry debit)
- **DTE alert** (5 days before front expiry)
- **Price movement** exceeds threshold (5% from strike)

### Email Flow

1. User approves signal → `userEmail` saved to `Position.user_email`
2. Position monitor detects exit condition → Sends alert to `Position.user_email`
3. User receives personalized email with position details and P&L

### Privy User Email

Access the user's email from Privy:

```typescript
import { usePrivy } from '@privy-io/react-auth';

function YourComponent() {
  const { user } = usePrivy();
  
  // Primary email (guaranteed for email/google/apple login)
  const userEmail = user?.email?.address;
  
  // Check if email is verified
  const isVerified = user?.email?.verified;
  
  // Use in API calls
  const approveSignal = async (signalId: string) => {
    await fetch(`/api/signals/${signalId}/approve`, {
      method: 'POST',
      body: JSON.stringify({
        userId: user.id,
        userEmail: userEmail,  // ← Add this
        // ... other fields
      })
    });
  };
}
```

### Error Handling

The backend will gracefully handle missing emails:
- If `userEmail` is not provided, position is still created
- Email alerts simply won't be sent for that position
- WebSocket alerts will still work

However, for best user experience, **always include the user's email**.

### Testing

1. Verify email is included in request payload
2. Check position is created with `user_email` field populated
3. Trigger an exit condition and verify email is received

```sql
-- Check if email is saved
SELECT id, symbol, user_id, user_email, status 
FROM positions 
WHERE user_id = 'did:privy:xxx';
```

---

## Implementation Checklist

- [ ] Update signal approval API call to include `userEmail`
- [ ] Handle case where user email might not be available
- [ ] Test email delivery for exit alerts
- [ ] Update any TypeScript types/interfaces
- [ ] Document the change in frontend README
