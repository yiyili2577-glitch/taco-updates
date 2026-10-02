from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Callable, Protocol
import time
import uuid


class ScanStage(str, Enum):
    ORDER = "order"
    ITEMS = "items"
    REVIEW = "review"
    COMMITTED = "committed"
    CANCELLED = "cancelled"


@dataclass(frozen=True)
class ScanEvent:
    event_id: str
    session_id: str
    actor_id: str
    event_type: str
    stage: str
    barcode: str
    created_at: float


@dataclass
class ScannedItem:
    sku: str
    barcode: str
    quantity: int = 1
    expected_quantity: int | None = None
    product_group: str = "default"


@dataclass(frozen=True)
class Destination:
    kind: str
    code: str
    container: str = ""
    location: str = ""
    zone: str = ""


@dataclass(frozen=True)
class Allocation:
    sku: str
    container: str
    location: str
    zone: str
    quantity: int
    rule_id: str


@dataclass
class ScanSession:
    actor_id: str
    session_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    stage: ScanStage = ScanStage.ORDER
    order_no: str | None = None
    items: dict[str, ScannedItem] = field(default_factory=dict)
    destination: Destination | None = None
    allocations: list[Allocation] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)

    @property
    def container(self) -> str | None:
        return self.destination.container if self.destination else None

    @property
    def location(self) -> str | None:
        return self.destination.location if self.destination else None

    @property
    def total_quantity(self) -> int:
        return sum(item.quantity for item in self.items.values())


class ScanError(ValueError):
    pass


class BusinessRuleError(ScanError):
    pass


class EventStore(Protocol):
    def append_pending(self, session: ScanSession) -> str: ...
    def mark_committed(self, event_id: str, receipt_id: str) -> None: ...
    def mark_failed(self, event_id: str, reason: str) -> None: ...


class AllocationPolicy:
    """Maps every item independently; a mixed order may fan out to several zones."""

    def __init__(self, rules: dict[str, dict] | None = None):
        self.rules = rules or {}

    def allocate(self, item: ScannedItem, destination: Destination) -> Allocation:
        rule = self.rules.get(item.sku) or self.rules.get(f"group:{item.product_group}") or {}
        location = str(rule.get("location") or destination.location).strip()
        zone = str(rule.get("zone") or destination.zone or "STAGING").strip()
        container = str(rule.get("container") or destination.container).strip()
        if not location:
            raise ScanError(f"品項 {item.sku} 找不到有效儲位，請先完成 Mapping")
        return Allocation(
            sku=item.sku,
            container=container,
            location=location,
            zone=zone,
            quantity=item.quantity,
            rule_id=str(rule.get("rule_id") or "destination-default"),
        )


class ReceiptBusinessRules:
    """Validates the complete intent immediately before the inventory transaction."""

    def validate(self, session: ScanSession) -> None:
        if not session.order_no:
            raise BusinessRuleError("缺少採購／收貨單號")
        if not session.items or session.total_quantity <= 0:
            raise BusinessRuleError("批次沒有可入庫品項")
        if len(session.allocations) != len(session.items):
            raise BusinessRuleError("部分品項尚未完成儲位分配")
        for item in session.items.values():
            if item.quantity <= 0:
                raise BusinessRuleError(f"品項 {item.sku} 數量必須大於零")
            if item.expected_quantity is not None and item.quantity > item.expected_quantity:
                raise BusinessRuleError(f"品項 {item.sku} 超過單據未收數量")


class _MemoryEventStore:
    """Compatibility fallback for embedding; production uses IntegrationEventStore."""

    def __init__(self):
        self.events: dict[str, dict] = {}

    def append_pending(self, session: ScanSession) -> str:
        event_id = str(uuid.uuid4())
        self.events[event_id] = {"state": "pending", "session": asdict(session)}
        return event_id

    def mark_committed(self, event_id: str, receipt_id: str) -> None:
        self.events[event_id].update(state="committed", receipt_id=receipt_id)

    def mark_failed(self, event_id: str, reason: str) -> None:
        self.events[event_id].update(state="failed", reason=reason)


class ScanWorkflow:
    """State machine that captures scan intent and never mutates inventory on scan."""

    def __init__(
        self,
        actor_id: str,
        resolver: Callable[[str], tuple[str, dict]],
        audit_sink: Callable[[ScanEvent], None],
        allocation_policy: AllocationPolicy | None = None,
    ):
        self.session = ScanSession(actor_id=actor_id)
        self._resolver = resolver
        self._audit_sink = audit_sink
        self._allocation_policy = allocation_policy or AllocationPolicy()

    def scan(self, barcode: str) -> ScanSession:
        barcode = barcode.strip()
        if not barcode:
            raise ScanError("條碼不可為空")
        kind, data = self._resolver(barcode)
        if self.session.stage == ScanStage.ORDER:
            self._scan_order(kind, data)
        elif self.session.stage == ScanStage.ITEMS:
            self._scan_item_or_destination(kind, data, barcode)
        else:
            raise ScanError("此批次已進入覆核或結案，請先確認、取消或建立新批次")
        self._audit("barcode_scanned", barcode)
        return self.session

    def _scan_order(self, kind: str, data: dict) -> None:
        if kind != "order" or not data.get("order_no"):
            raise ScanError("請先掃描有效單號")
        self.session.order_no = str(data["order_no"])
        self.session.stage = ScanStage.ITEMS

    def _scan_item_or_destination(self, kind: str, data: dict, barcode: str) -> None:
        if kind == "item":
            sku = str(data.get("sku") or "").strip()
            quantity = int(data.get("quantity", 1))
            if not sku or quantity <= 0:
                raise ScanError("貨品條碼資料無效")
            current = self.session.items.get(sku)
            if current:
                current.quantity += quantity
            else:
                self.session.items[sku] = ScannedItem(
                    sku=sku,
                    barcode=barcode,
                    quantity=quantity,
                    expected_quantity=data.get("expected_quantity"),
                    product_group=str(data.get("product_group") or "default"),
                )
            return
        if kind not in {"container", "location"}:
            raise ScanError("請連續掃貨品；完成後再掃容器或儲位")
        if not self.session.items:
            raise ScanError("至少需要一個貨品才能指定存放區域")
        destination = self._destination(kind, data)
        allocations = [self._allocation_policy.allocate(item, destination) for item in self.session.items.values()]
        self.session.destination = destination
        self.session.allocations = allocations
        self.session.stage = ScanStage.REVIEW

    @staticmethod
    def _destination(kind: str, data: dict) -> Destination:
        code = str(data.get("container") or data.get("location") or "").strip()
        location = str(data.get("location") or data.get("default_location") or "").strip()
        if not code:
            raise ScanError("容器／儲位條碼資料無效")
        if not location:
            raise ScanError("容器未對應有效儲位")
        return Destination(
            kind=kind,
            code=code,
            container=str(data.get("container") or ""),
            location=location,
            zone=str(data.get("zone") or "STAGING"),
        )

    def commit(
        self,
        inventory_service,
        permission_service,
        business_rules: ReceiptBusinessRules | None = None,
        event_store: EventStore | None = None,
    ) -> str:
        if self.session.stage != ScanStage.REVIEW:
            raise ScanError("尚未完成單號、貨品與目的地掃描")
        permission_service.require(self.session.actor_id, "inventory.receive")
        (business_rules or ReceiptBusinessRules()).validate(self.session)
        store = event_store or _MemoryEventStore()
        event_id = store.append_pending(self.session)
        try:
            receipt_id = inventory_service.commit_receipt(
                idempotency_key=self.session.session_id,
                session_id=self.session.session_id,
                order_no=self.session.order_no,
                allocations=self.session.allocations,
                actor_id=self.session.actor_id,
            )
        except Exception as exc:
            store.mark_failed(event_id, type(exc).__name__)
            self._audit("commit_failed", event_id)
            raise
        store.mark_committed(event_id, receipt_id)
        self.session.stage = ScanStage.COMMITTED
        self._audit("receipt_committed", receipt_id)
        return receipt_id

    def cancel(self, reason: str) -> None:
        if self.session.stage == ScanStage.COMMITTED:
            raise ScanError("已入庫批次不可取消，請走沖銷流程")
        self.session.stage = ScanStage.CANCELLED
        self._audit("session_cancelled", reason[:200])

    def new_session(self) -> ScanSession:
        self.session = ScanSession(actor_id=self.session.actor_id)
        return self.session

    def _audit(self, event_type: str, barcode: str) -> None:
        self._audit_sink(
            ScanEvent(
                event_id=str(uuid.uuid4()),
                session_id=self.session.session_id,
                actor_id=self.session.actor_id,
                event_type=event_type,
                stage=self.session.stage.value,
                barcode=barcode,
                created_at=time.time(),
            )
        )
