-- AlterTable
ALTER TABLE "calibration_runs"
ADD COLUMN "idempotencyKey" TEXT;

-- CreateIndex
CREATE UNIQUE INDEX "calibration_runs_idempotencyKey_key"
ON "calibration_runs"("idempotencyKey");
