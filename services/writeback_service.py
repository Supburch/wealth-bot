import asyncio
import hashlib
import json
import logging

from core.redaction import mask_id
from models.validation import ValidationResult, ValidationSummary
from repositories.validation_result_repository import ValidationResultRepository
from services.cache import check_and_set_idempotency, clear_idempotency

logger = logging.getLogger(__name__)


class WriteBackService:
    """Coordinates write-back of validation summaries."""

    def __init__(self, result_repository: ValidationResultRepository):
        self.result_repository = result_repository

    def _generate_idempotency_key(self, spreadsheet_id: str, summary: ValidationSummary) -> str:
        payload = json.dumps(
            summary.model_dump(mode="json"),
            sort_keys=True,
            separators=(",", ":"),
        )
        data_hash = hashlib.sha256(payload.encode("utf-8")).hexdigest()
        return f"writeback:{spreadsheet_id}:{data_hash}"

    async def write_validation_result(
        self,
        spreadsheet_id: str,
        summary: ValidationSummary,
    ) -> ValidationResult | None:
        key = self._generate_idempotency_key(spreadsheet_id, summary)
        spreadsheet_ref = mask_id(spreadsheet_id)
        is_duplicate = await check_and_set_idempotency(key, ttl=300)
        
        if is_duplicate:
            logger.info("Idempotency hit: skipping writeback for %s", spreadsheet_ref)
            return None

        result = ValidationResult(spreadsheet_id=spreadsheet_id, summary=summary)
        
        max_retries = 3
        timeout_seconds = 10.0
        
        for attempt in range(1, max_retries + 1):
            try:
                # Run the synchronous save in a thread with a timeout
                await asyncio.wait_for(
                    asyncio.to_thread(self.result_repository.save_result, result),
                    timeout=timeout_seconds,
                )
                logger.info("Successfully wrote validation result for %s", spreadsheet_ref)
                return result
            except TimeoutError:
                # asyncio.TimeoutError is deprecated in 3.11+ in favor of built-in TimeoutError
                logger.warning(
                    "Writeback timeout (attempt %d/%d) for %s",
                    attempt,
                    max_retries,
                    spreadsheet_ref,
                )
                if attempt == max_retries:
                    logger.error("All writeback retries failed for %s", spreadsheet_ref)
                    await clear_idempotency(key)
                    raise
                await asyncio.sleep(2 ** (attempt - 1))
            except Exception as e:
                logger.warning(
                    "Writeback failed (attempt %d/%d) for %s: %s",
                    attempt,
                    max_retries,
                    spreadsheet_ref,
                    type(e).__name__,
                )
                if attempt == max_retries:
                    logger.error("All writeback retries failed for %s", spreadsheet_ref)
                    await clear_idempotency(key)
                    raise
                await asyncio.sleep(2 ** (attempt - 1))

        return result
