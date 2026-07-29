# Game-phase classification

Deterministic method used by Check Yourself Stage 1:

1. Count non-king, non-pawn pieces (`N+B+R+Q` for both sides) as `pieces`.
2. **Endgame** if:
   - `pieces <= 6`, or
   - both queens are off the board and `pieces <= 8`.
3. **Opening** if not endgame and either:
   - `fullmove_number <= 10` and `pieces >= 12`, or
   - some castling rights remain, `pieces >= 10`, and `fullmove_number <= 16`.
4. Otherwise **middlegame**.

This favors board features over move number alone while remaining simple and
unit-testable.
