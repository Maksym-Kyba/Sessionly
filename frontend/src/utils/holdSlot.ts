import { createBooking } from "@/api/booking";
import { errorStatus } from "@/api/errors";
import {
  clearGrant,
  clearPendingSelection,
  type PendingSelection,
  saveBookingAccess,
  savePendingRecovery,
  type StoredGrant,
} from "@/utils/clientBookingStorage";

/** Outcome of an attempt to hold a slot with a verification grant. */
export type HoldSlotResult =
  | { kind: "held"; bookingId: string }
  /** The slot was taken meanwhile. The grant was not consumed and can be reused. */
  | { kind: "slot-taken" }
  /** The grant is invalid, expired or already used; the client must verify the email again. */
  | { kind: "verification-invalid" }
  /**
   * The booking was created earlier but no access token was returned for this browser. It is saved
   * as a pending recovery; the client verifies the email again to recover access.
   */
  | { kind: "no-access"; bookingId: string }
  | { kind: "error" };

type SlotSelection = Omit<PendingSelection, "savedAt">;

/**
 * Creates the 15-minute hold for the selected slot and stores the client access token.
 * The pending selection is cleared once the backend has answered definitively.
 */
export async function holdSlot(selection: SlotSelection, grant: StoredGrant): Promise<HoldSlotResult> {
  try {
    const booking = await createBooking(selection.slotId, grant.token, selection.idempotencyKey);
    clearPendingSelection();
    clearGrant();
    if (!booking.client_access_token) {
      savePendingRecovery({
        bookingId: booking.id,
        psychologistPublicId: selection.psychologistPublicId,
        psychologistName: selection.psychologistName,
        timeZone: selection.timeZone,
      });
      return { kind: "no-access", bookingId: booking.id };
    }
    saveBookingAccess(booking.id, {
      token: booking.client_access_token,
      expiresAt: booking.client_access_token_expires_at,
      psychologistPublicId: selection.psychologistPublicId,
      psychologistName: selection.psychologistName,
      timeZone: selection.timeZone,
    });
    return { kind: "held", bookingId: booking.id };
  } catch (error) {
    const status = errorStatus(error);
    if (status === 409) {
      clearPendingSelection();
      return { kind: "slot-taken" };
    }
    if (status === 400) {
      clearGrant();
      return { kind: "verification-invalid" };
    }
    return { kind: "error" };
  }
}
