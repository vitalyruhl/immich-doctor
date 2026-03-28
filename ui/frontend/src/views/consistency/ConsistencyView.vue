<template>
  <section class="page">
    <PageHeader
      eyebrow="Consistency"
      title="Missing asset references"
      summary="Review database entries that still reference physically missing original assets, preview safe removals, and manage restore points."
    />
    <DisclaimerBanner />
    <RiskNotice
      title="Exact scan scope"
      message="This screen only reviews original asset references that the backend can resolve to a concrete path. Present, missing_on_disk, permission_error, unreadable_path, unsupported, and already_removed stay distinct so operators do not have to guess what happened."
    />

    <LoadingState
      v-if="consistencyStore.isLoading && !hasAnyData"
      title="Loading missing asset references"
      message="Collecting scan findings and restore-point history from the backend."
    />
    <ErrorState
      v-else-if="initialLoadError && !hasAnyData"
      title="Consistency data unavailable"
      :message="initialLoadError"
    />

    <template v-else>
      <section class="health-grid">
        <article class="panel">
          <div class="health-card__header">
            <h3>Scan summary</h3>
            <StatusTag :status="scanStatusTag" />
          </div>
          <p class="health-card__summary">{{ consistencyStore.findings.length }} findings loaded</p>
          <p class="health-card__details">
            {{ consistencyStore.scanResult?.summary ?? 'No scan has been run yet.' }}
          </p>
          <dl class="runtime-detail__grid">
            <dt>Scan tables</dt>
            <dd>{{ scanTablesLabel }}</dd>
            <dt>Path field</dt>
            <dd>{{ scanPathFieldLabel }}</dd>
            <dt>Restore tables</dt>
            <dd>{{ repairTablesLabel }}</dd>
            <dt>Blocking issues</dt>
            <dd>{{ blockingIssuesLabel }}</dd>
          </dl>
        </article>
        <article class="panel">
          <div class="health-card__header">
            <h3>Missing on disk</h3>
            <StatusTag :status="missingStatusTag" />
          </div>
          <p class="health-card__summary">{{ missingOnDiskCount }} records</p>
          <p class="health-card__details">Only entries with a real on-disk path check are shown here.</p>
        </article>
        <article class="panel">
          <div class="health-card__header">
            <h3>Repair readiness</h3>
            <StatusTag :status="readyStatusTag" />
          </div>
          <p class="health-card__summary">{{ readyForRepairCount }} ready</p>
          <p class="health-card__details">
            {{ blockedForRepairCount }} blocked by path, permission, or support issues.
          </p>
        </article>
        <article class="panel">
          <div class="health-card__header">
            <h3>Restore points</h3>
            <StatusTag :status="restorePointStatusTag" />
          </div>
          <p class="health-card__summary">{{ consistencyStore.restorePoints.length }} available</p>
          <p class="health-card__details">
            Restore points are reversible state until deleted explicitly.
          </p>
        </article>
      </section>

      <section class="panel consistency-section">
        <div class="settings-section__header">
          <div>
            <h3>Findings review</h3>
            <p>Filter, sort, select, and preview removals from the current scan result.</p>
          </div>
          <div class="runtime-actions">
            <button
              class="runtime-action runtime-action--secondary"
              type="button"
              :disabled="consistencyStore.isScanning"
              @click="void refreshScan()"
            >
              {{ consistencyStore.isScanning ? 'Rescanning' : 'Rescan findings' }}
            </button>
            <button
              class="runtime-action"
              type="button"
              :disabled="!selectedRepairableFindings.length || consistencyStore.isPreviewing"
              @click="void previewSelected()"
            >
              Preview selected ({{ selectedRepairableFindings.length }})
            </button>
            <button
              class="runtime-action"
              type="button"
              :disabled="!consistencyStore.findings.length || consistencyStore.isPreviewing"
              @click="void previewAll()"
            >
              Preview all ({{ consistencyStore.findings.length }})
            </button>
          </div>
        </div>

        <section class="consistency-filter-bar">
          <label class="backup-form__field">
            <span>Search</span>
            <input
              v-model="searchTerm"
              type="search"
              placeholder="Asset id, owner, path, status, or blocker"
            />
          </label>
          <label class="backup-form__field">
            <span>Status</span>
            <select v-model="statusFilter">
              <option value="all">All statuses</option>
              <option v-for="status in findingStatusOptions" :key="status" :value="status">
                {{ formatFindingStatus(status) }}
              </option>
            </select>
          </label>
          <label class="backup-form__field">
            <span>Repair readiness</span>
            <select v-model="readinessFilter">
              <option value="all">All readiness states</option>
              <option value="ready">Ready</option>
              <option value="blocked">Blocked</option>
            </select>
          </label>
          <div class="consistency-filter-bar__summary">
            <strong>{{ sortedFindings.length }}</strong>
            <span>visible findings</span>
            <small>{{ selectedFindingIds.length }} selected</small>
          </div>
        </section>

        <ErrorState
          v-if="consistencyStore.scanError"
          title="Scan findings unavailable"
          :message="consistencyStore.scanError"
        />
        <div v-else class="consistency-table-wrap">
          <table class="consistency-table">
            <thead>
              <tr>
                <th class="consistency-table__checkbox-cell">
                  <input
                    type="checkbox"
                    :checked="allVisibleFindingsSelected"
                    :disabled="!visibleRepairableFindingIds.length"
                    aria-label="Select all visible findings"
                    @change="toggleAllVisibleFindings(($event.target as HTMLInputElement).checked)"
                  />
                </th>
                <th v-for="column in findingColumns" :key="column.key">
                  <button
                    type="button"
                    class="consistency-table__sort"
                    @click="toggleFindingSort(column.key)"
                  >
                    {{ column.label }} <span>{{ sortGlyph(column.key) }}</span>
                  </button>
                </th>
                <th>Blockers</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="finding in sortedFindings" :key="finding.finding_id">
                <td class="consistency-table__checkbox-cell">
                  <input
                    type="checkbox"
                    :checked="selectedFindingSet.has(finding.finding_id)"
                    :disabled="!isRepairableFinding(finding)"
                    :aria-label="`Select finding ${finding.finding_id}`"
                    @change="toggleFindingSelection(finding.finding_id)"
                  />
                </td>
                <td class="consistency-table__cell consistency-table__cell--mono">
                  {{ finding.asset_id }}
                </td>
                <td class="consistency-table__cell">{{ finding.owner_id ?? 'Unavailable' }}</td>
                <td class="consistency-table__cell">{{ finding.asset_type }}</td>
                <td class="consistency-table__cell consistency-table__cell--path">
                  {{ finding.logical_path }}
                </td>
                <td class="consistency-table__cell consistency-table__cell--path">
                  {{ finding.resolved_physical_path }}
                </td>
                <td class="consistency-table__cell">
                  <span :class="findingStatusClass(finding.status)" class="consistency-chip">
                    {{ formatFindingStatus(finding.status) }}
                  </span>
                </td>
                <td class="consistency-table__cell">
                  <span :class="readinessStatusClass(finding.repair_readiness)" class="consistency-chip">
                    {{ finding.repair_readiness }}
                  </span>
                </td>
                <td class="consistency-table__cell">{{ formatDate(finding.created_at) }}</td>
                <td class="consistency-table__cell">{{ formatDate(finding.updated_at) }}</td>
                <td class="consistency-table__cell">{{ formatDate(finding.scan_timestamp) }}</td>
                <td class="consistency-table__cell consistency-table__cell--path">
                  {{ finding.repair_blockers.length ? finding.repair_blockers.join(' • ') : 'None' }}
                </td>
                <td class="consistency-table__cell">
                  <button
                    type="button"
                    class="runtime-action runtime-action--secondary"
                    :disabled="!isRepairableFinding(finding) || consistencyStore.isPreviewing"
                    @click="void previewSingle(finding)"
                  >
                    Preview single
                  </button>
                </td>
              </tr>
              <tr v-if="!sortedFindings.length">
                <td class="consistency-empty-row" :colspan="findingColumns.length + 3">
                  No findings match the current filters.
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>

      <section class="settings-grid">
        <article class="panel consistency-preview">
          <div class="settings-section__header">
            <div>
              <h3>Preview and apply</h3>
              <p>Preview is required before apply. Apply remains disabled until both safety checkboxes are checked.</p>
            </div>
            <StatusTag :status="previewStatusTag" />
          </div>
          <p class="health-card__summary">{{ previewResult?.summary ?? 'No preview has been generated yet.' }}</p>
          <dl class="runtime-detail__grid">
            <dt>Preview scope</dt>
            <dd>{{ previewScopeLabel }}</dd>
            <dt>Repair run</dt>
            <dd>{{ previewResult?.repair_run_id ?? 'Unavailable' }}</dd>
            <dt>Preview count</dt>
            <dd>{{ previewResult?.selected_findings.length ?? 0 }}</dd>
          </dl>
          <p v-if="consistencyStore.previewError" class="runtime-blocking-message">{{ consistencyStore.previewError }}</p>
          <p v-if="consistencyStore.applyError" class="runtime-blocking-message">{{ consistencyStore.applyError }}</p>
          <p v-if="previewDriftMessage" class="runtime-blocking-message">{{ previewDriftMessage }}</p>
          <section v-if="previewResult?.selected_findings.length" class="runtime-findings">
            <article
              v-for="item in previewResult.selected_findings"
              :key="item.finding_id"
              class="runtime-finding"
            >
              <div class="runtime-finding__header">
                <strong>{{ item.asset_id }}</strong>
                <span :class="findingStatusClass(item.status)" class="consistency-chip">
                  {{ formatFindingStatus(item.status) }}
                </span>
              </div>
              <span>{{ item.logical_path }}</span>
              <small>{{ item.resolved_physical_path }}</small>
            </article>
          </section>
          <section class="consistency-disclaimer">
            <h4>Repair disclaimer</h4>
            <p>
              Before applying removal, ensure both the database backup and the asset/storage backup exist.
            </p>
            <label class="consistency-disclaimer__check">
              <input v-model="warningRead" type="checkbox" />
              <span>I have read the warning</span>
            </label>
            <label class="consistency-disclaimer__check">
              <input v-model="backupCreated" type="checkbox" />
              <span>I created a backup</span>
            </label>
            <div class="runtime-actions">
              <button
                type="button"
                class="runtime-action runtime-action--danger"
                :disabled="applyDisabled"
                @click="void applyPreviewedRemoval()"
              >
                {{ applyButtonLabel }}
              </button>
            </div>
            <p v-if="applyDisabledMessage" class="runtime-blocking-message">
              {{ applyDisabledMessage }}
            </p>
          </section>
          <article v-if="applyResult" class="runtime-finding">
            <div class="runtime-finding__header">
              <strong>Latest apply result</strong>
              <StatusTag :status="operationStatusTag(applyResult.status)" />
            </div>
            <span>{{ applyResult.summary }}</span>
            <small>repair_run_id={{ applyResult.repair_run_id }}</small>
          </article>
        </article>

        <article class="panel consistency-restore">
          <div class="settings-section__header">
            <div>
              <h3>Restore points</h3>
              <p>Restore and delete remain separate operations.</p>
            </div>
            <StatusTag :status="restorePointStatusTag" />
          </div>
          <p class="health-card__summary">{{ consistencyStore.restorePoints.length }} restore points available</p>
          <section class="runtime-actions consistency-actions">
            <button
              type="button"
              class="runtime-action"
              :disabled="!selectedRestorePointIds.length || consistencyStore.isRestoring"
              @click="void restoreSelectedRestorePoints()"
            >
              Restore selected ({{ selectedRestorePointIds.length }})
            </button>
            <button
              type="button"
              class="runtime-action"
              :disabled="!consistencyStore.restorePoints.length || consistencyStore.isRestoring"
              @click="void restoreAllRestorePoints()"
            >
              Restore all ({{ consistencyStore.restorePoints.length }})
            </button>
          </section>
          <p v-if="consistencyStore.restoreError" class="runtime-blocking-message">
            {{ consistencyStore.restoreError }}
          </p>
          <div class="consistency-table-wrap">
            <table class="consistency-table">
              <thead>
                <tr>
                  <th class="consistency-table__checkbox-cell">
                    <input
                      type="checkbox"
                      :checked="allRestorePointsSelected"
                      :disabled="!consistencyStore.restorePoints.length"
                      aria-label="Select all restore points"
                      @change="toggleAllRestorePoints(($event.target as HTMLInputElement).checked)"
                    />
                  </th>
                  <th>Restore point</th>
                  <th>Repair run</th>
                  <th>Asset</th>
                  <th>Status</th>
                  <th>Records</th>
                  <th>Created</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="restorePoint in consistencyStore.restorePoints" :key="restorePoint.restore_point_id">
                  <td class="consistency-table__checkbox-cell">
                    <input
                      type="checkbox"
                      :checked="selectedRestorePointSet.has(restorePoint.restore_point_id)"
                      :aria-label="`Select restore point ${restorePoint.restore_point_id}`"
                      @change="toggleRestorePointSelection(restorePoint.restore_point_id)"
                    />
                  </td>
                  <td class="consistency-table__cell consistency-table__cell--mono">
                    {{ restorePoint.restore_point_id }}
                  </td>
                  <td class="consistency-table__cell consistency-table__cell--mono">
                    {{ restorePoint.repair_run_id }}
                  </td>
                  <td class="consistency-table__cell consistency-table__cell--mono">
                    {{ restorePoint.asset_id }}
                  </td>
                  <td class="consistency-table__cell">
                    <span :class="restorePointStatusClass(restorePoint.status)" class="consistency-chip">
                      {{ formatRestorePointStatus(restorePoint.status) }}
                    </span>
                  </td>
                  <td class="consistency-table__cell">
                    <div class="consistency-table__stack">
                      <strong>{{ restorePoint.record_count }}</strong>
                      <small>{{ formatRestoreRecords(restorePoint.records) }}</small>
                    </div>
                  </td>
                  <td class="consistency-table__cell">{{ formatDate(restorePoint.created_at) }}</td>
                  <td class="consistency-table__cell">
                    <div class="runtime-actions consistency-row-actions">
                      <button
                        type="button"
                        class="runtime-action runtime-action--secondary"
                        :disabled="consistencyStore.isRestoring"
                        @click="void restoreSingleRestorePoint(restorePoint.restore_point_id)"
                      >
                        Restore
                      </button>
                      <button
                        type="button"
                        class="runtime-action runtime-action--danger"
                        :disabled="consistencyStore.isDeletingRestorePoints"
                        @click="openDeleteDialog([restorePoint.restore_point_id], false)"
                      >
                        Delete
                      </button>
                    </div>
                  </td>
                </tr>
                <tr v-if="!consistencyStore.restorePoints.length">
                  <td class="consistency-empty-row" colspan="8">No restore points available.</td>
                </tr>
              </tbody>
            </table>
          </div>

          <section class="consistency-delete-zone">
            <div class="settings-section__header">
              <div>
                <h4>Delete restore points</h4>
                <p>Deletion is intentionally separated from restore and requires explicit confirmation.</p>
              </div>
            </div>
            <section class="runtime-actions consistency-actions consistency-actions--danger">
              <button
                type="button"
                class="runtime-action runtime-action--danger"
                :disabled="!selectedRestorePointIds.length || consistencyStore.isDeletingRestorePoints"
                @click="openDeleteDialog(selectedRestorePointIds, false)"
              >
                Delete selected ({{ selectedRestorePointIds.length }})
              </button>
              <button
                type="button"
                class="runtime-action runtime-action--danger"
                :disabled="!consistencyStore.restorePoints.length || consistencyStore.isDeletingRestorePoints"
                @click="openDeleteDialog(consistencyStore.restorePoints.map((item) => item.restore_point_id), true)"
              >
                Delete all ({{ consistencyStore.restorePoints.length }})
              </button>
            </section>
            <p v-if="consistencyStore.deleteError" class="runtime-blocking-message">
              {{ consistencyStore.deleteError }}
            </p>
          </section>

          <article v-if="restoreResult" class="runtime-finding">
            <div class="runtime-finding__header">
              <strong>Latest restore result</strong>
              <StatusTag :status="operationStatusTag(restoreResult.status)" />
            </div>
            <span>{{ restoreResult.summary }}</span>
          </article>
          <article v-if="deleteResult" class="runtime-finding">
            <div class="runtime-finding__header">
              <strong>Latest delete result</strong>
              <StatusTag :status="operationStatusTag(deleteResult.status)" />
            </div>
            <span>{{ deleteResult.summary }}</span>
          </article>
        </article>
      </section>
    </template>

    <ConfirmOperationDialog
      :visible="showDeleteDialog"
      title="Delete restore points"
      :summary="deleteDialogSummary"
      :items="deleteDialogItems"
      :notes="deleteDialogNotes"
      confirm-label="Delete restore points"
      cancel-label="Cancel"
      :confirm-disabled="consistencyStore.isDeletingRestorePoints"
      @cancel="closeDeleteDialog"
      @confirm="void confirmDeleteRestorePoints()"
    />
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import ConfirmOperationDialog from '@/components/safety/ConfirmOperationDialog.vue';
import DisclaimerBanner from '@/components/safety/DisclaimerBanner.vue';
import ErrorState from '@/components/common/ErrorState.vue';
import LoadingState from '@/components/common/LoadingState.vue';
import PageHeader from '@/components/common/PageHeader.vue';
import RiskNotice from '@/components/safety/RiskNotice.vue';
import StatusTag from '@/components/common/StatusTag.vue';
import { useConsistencyStore } from '@/stores/consistency';
import type { HealthState } from '@/api/types/common';
import type {
  MissingAssetApplyResponse,
  MissingAssetPreviewResponse,
  MissingAssetReferenceFinding,
  MissingAssetReferenceStatus,
  MissingAssetRestorePoint,
  MissingAssetRestorePointDeleteRequest,
  MissingAssetRestorePointDeleteResponse,
  MissingAssetRestoreResponse,
  RepairReadinessStatus,
} from '@/api/types/consistency';

type FindingSortField =
  | 'asset_id'
  | 'owner_id'
  | 'asset_type'
  | 'logical_path'
  | 'resolved_physical_path'
  | 'status'
  | 'created_at'
  | 'updated_at'
  | 'scan_timestamp'
  | 'repair_readiness';

interface FindingColumn {
  key: FindingSortField;
  label: string;
}

interface SupportedScopeMetadata {
  scanTables?: unknown;
  scanPathField?: unknown;
  repairRestoreTables?: unknown;
  blockingIssues?: unknown;
}

const findingColumns: FindingColumn[] = [
  { key: 'asset_id', label: 'Asset id' },
  { key: 'owner_id', label: 'Owner / user' },
  { key: 'asset_type', label: 'Asset type' },
  { key: 'logical_path', label: 'Logical path' },
  { key: 'resolved_physical_path', label: 'Resolved physical path' },
  { key: 'status', label: 'Status' },
  { key: 'repair_readiness', label: 'Readiness' },
  { key: 'created_at', label: 'Created' },
  { key: 'updated_at', label: 'Updated' },
  { key: 'scan_timestamp', label: 'Scan' },
];

const findingStatusOptions: MissingAssetReferenceStatus[] = [
  'present',
  'missing_on_disk',
  'permission_error',
  'unreadable_path',
  'unsupported',
  'already_removed',
];

const dateFormatter = new Intl.DateTimeFormat(undefined, {
  dateStyle: 'medium',
  timeStyle: 'short',
});

const consistencyStore = useConsistencyStore();
const searchTerm = ref('');
const statusFilter = ref<MissingAssetReferenceStatus | 'all'>('all');
const readinessFilter = ref<RepairReadinessStatus | 'all'>('all');
const sortField = ref<FindingSortField>('status');
const sortDirection = ref<'asc' | 'desc'>('asc');
const selectedFindingIds = ref<string[]>([]);
const selectedRestorePointIds = ref<string[]>([]);
const warningRead = ref(false);
const backupCreated = ref(false);
const previewResult = ref<MissingAssetPreviewResponse | null>(null);
const applyResult = ref<MissingAssetApplyResponse | null>(null);
const restoreResult = ref<MissingAssetRestoreResponse | null>(null);
const deleteResult = ref<MissingAssetRestorePointDeleteResponse | null>(null);
const previewContext = ref<{ mode: 'single' | 'selected' | 'all'; selectionKey: string; fingerprint: string } | null>(null);
const showDeleteDialog = ref(false);
const pendingDeleteRestorePointIds = ref<string[]>([]);
const pendingDeleteSelectAll = ref(false);

const selectedFindingSet = computed(() => new Set(selectedFindingIds.value));
const selectedRestorePointSet = computed(() => new Set(selectedRestorePointIds.value));
const selectedRepairableFindings = computed(() =>
  selectedFindingIds.value
    .map((findingId) => consistencyStore.findings.find((finding) => finding.finding_id === findingId))
    .filter(
      (finding): finding is MissingAssetReferenceFinding =>
        finding !== undefined && isRepairableFinding(finding),
    ),
);
const filteredFindings = computed(() => {
  const query = searchTerm.value.trim().toLowerCase();
  return consistencyStore.findings.filter((finding) => {
    if (statusFilter.value !== 'all' && finding.status !== statusFilter.value) {
      return false;
    }
    if (readinessFilter.value !== 'all' && finding.repair_readiness !== readinessFilter.value) {
      return false;
    }
    if (!query) {
      return true;
    }
    const haystack = [
      finding.finding_id,
      finding.asset_id,
      finding.owner_id ?? '',
      finding.asset_type,
      finding.logical_path,
      finding.resolved_physical_path,
      finding.status,
      finding.repair_readiness,
      finding.message,
      ...finding.repair_blockers,
    ]
      .join(' ')
      .toLowerCase();
    return haystack.includes(query);
  });
});
const sortedFindings = computed(() => {
  const items = [...filteredFindings.value];
  items.sort((left, right) => {
    let result = 0;
    switch (sortField.value) {
      case 'asset_id':
        result = compareStrings(left.asset_id, right.asset_id);
        break;
      case 'owner_id':
        result = compareStrings(left.owner_id, right.owner_id);
        break;
      case 'asset_type':
        result = compareStrings(left.asset_type, right.asset_type);
        break;
      case 'logical_path':
        result = compareStrings(left.logical_path, right.logical_path);
        break;
      case 'resolved_physical_path':
        result = compareStrings(left.resolved_physical_path, right.resolved_physical_path);
        break;
      case 'status':
        result = compareStrings(left.status, right.status);
        break;
      case 'created_at':
        result = compareDates(left.created_at, right.created_at);
        break;
      case 'updated_at':
        result = compareDates(left.updated_at, right.updated_at);
        break;
      case 'scan_timestamp':
        result = compareDates(left.scan_timestamp, right.scan_timestamp);
        break;
      case 'repair_readiness':
        result = compareStrings(left.repair_readiness, right.repair_readiness);
        break;
    }
    return sortDirection.value === 'asc' ? result : -result;
  });
  return items;
});
const visibleRepairableFindingIds = computed(() =>
  sortedFindings.value.filter((finding) => isRepairableFinding(finding)).map((finding) => finding.finding_id),
);
const allVisibleFindingsSelected = computed(
  () =>
    visibleRepairableFindingIds.value.length > 0 &&
    visibleRepairableFindingIds.value.every((findingId) => selectedFindingSet.value.has(findingId)),
);
const allRestorePointsSelected = computed(
  () =>
    consistencyStore.restorePoints.length > 0 &&
    consistencyStore.restorePoints.every((item) => selectedRestorePointSet.value.has(item.restore_point_id)),
);
const hasAnyData = computed(
  () => consistencyStore.findings.length > 0 || consistencyStore.restorePoints.length > 0,
);
const initialLoadError = computed(() => consistencyStore.scanError ?? consistencyStore.restorePointsError ?? null);
const missingOnDiskCount = computed(
  () => consistencyStore.findings.filter((finding) => finding.status === 'missing_on_disk').length,
);
const readyForRepairCount = computed(
  () => consistencyStore.findings.filter((finding) => finding.repair_readiness === 'ready').length,
);
const blockedForRepairCount = computed(
  () => consistencyStore.findings.filter((finding) => finding.repair_readiness === 'blocked').length,
);
const scanStatusTag = computed(() => toHealthState(consistencyStore.scanError, consistencyStore.scanResult));
const missingStatusTag = computed<HealthState>(() => (missingOnDiskCount.value > 0 ? 'warning' : 'ok'));
const readyStatusTag = computed<HealthState>(() => (blockedForRepairCount.value > 0 ? 'warning' : 'ok'));
const restorePointStatusTag = computed(() =>
  toHealthState(consistencyStore.restorePointsError, consistencyStore.restorePointsResult),
);
const previewStatusTag = computed<HealthState>(() => {
  if (consistencyStore.previewError) {
    return 'error';
  }
  if (!previewResult.value) {
    return 'unknown';
  }
  return operationStatusTag(previewResult.value.status);
});
const currentSelectionKey = computed(() => buildSelectionKey(selectedFindingIds.value));
const currentScanFingerprint = computed(() => fingerprintFindings(consistencyStore.findings));
const supportedScope = computed<SupportedScopeMetadata | null>(() => {
  const scope = consistencyStore.scanResult?.metadata?.supportedScope;
  return scope && typeof scope === 'object' ? (scope as SupportedScopeMetadata) : null;
});
const scanTablesLabel = computed(() => formatListValue(supportedScope.value?.scanTables));
const scanPathFieldLabel = computed(() => formatValue(supportedScope.value?.scanPathField));
const repairTablesLabel = computed(() => formatListValue(supportedScope.value?.repairRestoreTables));
const blockingIssuesLabel = computed(() => {
  const rawIssues = supportedScope.value?.blockingIssues;
  if (Array.isArray(rawIssues)) {
    const items = rawIssues.filter(
      (item): item is string => typeof item === 'string' && item.trim().length > 0,
    );
    return items.length ? items.join(', ') : 'None';
  }
  return formatValue(rawIssues) === 'Unavailable' ? 'None' : formatValue(rawIssues);
});
const previewDriftMessage = computed(() => {
  if (!previewResult.value || !previewContext.value) {
    return null;
  }
  if (previewContext.value.fingerprint !== currentScanFingerprint.value) {
    return 'Preview drift detected: the scan result changed after preview.';
  }
  if (previewContext.value.mode !== 'all' && previewContext.value.selectionKey !== currentSelectionKey.value) {
    return 'Preview drift detected: the selected rows changed after preview.';
  }
  return null;
});
const applyDisabledMessage = computed(() => {
  if (consistencyStore.isPreviewing || consistencyStore.isApplying) {
    return 'An action is already running.';
  }
  if (!previewResult.value) {
    return 'Preview a selection before apply.';
  }
  if (!warningRead.value || !backupCreated.value) {
    return 'Both confirmations are required before apply.';
  }
  if (previewDriftMessage.value) {
    return previewDriftMessage.value;
  }
  return null;
});
const applyDisabled = computed(() => Boolean(applyDisabledMessage.value));
const applyButtonLabel = computed(() => {
  if (previewContext.value?.mode === 'all') {
    return 'Apply all removals';
  }
  if (previewContext.value?.mode === 'selected') {
    return 'Apply selected removals';
  }
  return 'Apply single removal';
});
const previewScopeLabel = computed(() => {
  if (!previewResult.value || !previewContext.value) {
    return 'No preview';
  }
  if (previewContext.value.mode === 'all') {
    return `All findings (${previewResult.value.selected_findings.length})`;
  }
  if (previewContext.value.mode === 'selected') {
    return `Selected findings (${previewResult.value.selected_findings.length})`;
  }
  return `Single finding (${previewResult.value.selected_findings[0]?.asset_id ?? 'unknown'})`;
});
const deleteDialogSummary = computed(() =>
  pendingDeleteSelectAll.value
    ? 'This will delete all restore points and remove their reversible state.'
    : 'This will delete the selected restore points and remove their reversible state.',
);
const deleteDialogItems = computed(() =>
  pendingDeleteRestorePointIds.value.map((restorePointId) => `restore_point_id=${restorePointId}`),
);
const deleteDialogNotes = computed(() => [
  'Delete is separate from restore and cannot be used as a recovery step.',
  'Operators should confirm the delete target list before proceeding.',
]);

function formatValue(value: unknown): string {
  if (typeof value === 'string' && value.trim()) {
    return value;
  }
  return 'Unavailable';
}

function formatListValue(value: unknown): string {
  if (Array.isArray(value)) {
    const items = value.filter(
      (item): item is string => typeof item === 'string' && item.trim().length > 0,
    );
    return items.length ? items.join(', ') : 'Unavailable';
  }
  return formatValue(value);
}

function formatDate(value: string | null): string {
  if (!value) {
    return 'Unavailable';
  }
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? value : dateFormatter.format(parsed);
}

function formatFindingStatus(status: MissingAssetReferenceStatus): string {
  return status.replace(/_/g, ' ');
}

function formatRestorePointStatus(status: MissingAssetRestorePoint['status']): string {
  return status.replace(/_/g, ' ');
}

function formatRestoreRecords(records: MissingAssetRestorePoint['records']): string {
  return records.length
    ? records.map((record) => `${record.table}:${record.row_count}`).join(', ')
    : 'No record summary';
}

function buildSelectionKey(ids: string[]): string {
  return [...new Set(ids)].sort().join('|');
}

function fingerprintFindings(findings: MissingAssetReferenceFinding[]): string {
  return findings
    .map((finding) =>
      [finding.finding_id, finding.asset_id, finding.status, finding.repair_readiness, finding.scan_timestamp].join(':'),
    )
    .sort()
    .join('|');
}

function compareStrings(left: string | null, right: string | null): number {
  return (left ?? '').localeCompare(right ?? '');
}

function compareDates(left: string | null, right: string | null): number {
  const leftTime = left ? Date.parse(left) : Number.NEGATIVE_INFINITY;
  const rightTime = right ? Date.parse(right) : Number.NEGATIVE_INFINITY;
  return leftTime - rightTime;
}

function sortGlyph(field: FindingSortField): string {
  if (sortField.value !== field) {
    return '-';
  }
  return sortDirection.value === 'asc' ? '^' : 'v';
}

function toggleFindingSort(field: FindingSortField): void {
  if (sortField.value === field) {
    sortDirection.value = sortDirection.value === 'asc' ? 'desc' : 'asc';
    return;
  }
  sortField.value = field;
  sortDirection.value = 'asc';
}

function isRepairableFinding(finding: MissingAssetReferenceFinding): boolean {
  return finding.status === 'missing_on_disk' && finding.repair_readiness === 'ready';
}

function findingStatusClass(status: MissingAssetReferenceStatus): string {
  return `consistency-chip--finding-${status}`;
}

function readinessStatusClass(status: RepairReadinessStatus): string {
  return `consistency-chip--readiness-${status}`;
}

function restorePointStatusClass(status: MissingAssetRestorePoint['status']): string {
  return `consistency-chip--restore-${status}`;
}

function toggleFindingSelection(findingId: string): void {
  const finding = consistencyStore.findings.find((item) => item.finding_id === findingId);
  if (!finding || !isRepairableFinding(finding)) {
    return;
  }
  selectedFindingIds.value = selectedFindingIds.value.includes(findingId)
    ? selectedFindingIds.value.filter((item) => item !== findingId)
    : [...selectedFindingIds.value, findingId];
}

function toggleAllVisibleFindings(checked: boolean): void {
  const visibleIds = visibleRepairableFindingIds.value;
  selectedFindingIds.value = checked
    ? Array.from(new Set([...selectedFindingIds.value, ...visibleIds]))
    : selectedFindingIds.value.filter((item) => !visibleIds.includes(item));
}

function toggleRestorePointSelection(restorePointId: string): void {
  selectedRestorePointIds.value = selectedRestorePointIds.value.includes(restorePointId)
    ? selectedRestorePointIds.value.filter((item) => item !== restorePointId)
    : [...selectedRestorePointIds.value, restorePointId];
}

function toggleAllRestorePoints(checked: boolean): void {
  selectedRestorePointIds.value = checked
    ? consistencyStore.restorePoints.map((item) => item.restore_point_id)
    : [];
}

function reconcileSelections(): void {
  selectedFindingIds.value = selectedFindingIds.value.filter((findingId) =>
    consistencyStore.findings.some(
      (finding) => finding.finding_id === findingId && isRepairableFinding(finding),
    ),
  );
  selectedRestorePointIds.value = selectedRestorePointIds.value.filter((restorePointId) =>
    consistencyStore.restorePoints.some((item) => item.restore_point_id === restorePointId),
  );
}

function clearPreviewState(): void {
  previewResult.value = null;
  previewContext.value = null;
  warningRead.value = false;
  backupCreated.value = false;
}

function operationStatusTag(status: string): HealthState {
  const normalized = status.toLowerCase();
  if (['pass', 'ok', 'success', 'applied', 'restored', 'deleted'].includes(normalized)) {
    return 'ok';
  }
  if (['warn', 'warning', 'planned', 'skipped', 'partial', 'already_removed'].includes(normalized)) {
    return 'warning';
  }
  if (['fail', 'failed', 'error'].includes(normalized)) {
    return 'error';
  }
  return 'unknown';
}

function toHealthState(
  error: string | null,
  result: { status?: string | null } | null,
): HealthState {
  if (error) {
    return 'error';
  }
  if (result?.status) {
    return operationStatusTag(result.status);
  }
  if (result) {
    return 'ok';
  }
  return 'unknown';
}

async function refreshScan(): Promise<void> {
  clearPreviewState();
  await consistencyStore.scan();
  reconcileSelections();
}

async function previewSingle(finding: MissingAssetReferenceFinding): Promise<void> {
  if (!isRepairableFinding(finding)) {
    return;
  }
  const result = await consistencyStore.preview({
    asset_ids: [finding.asset_id],
    select_all: false,
    limit: 1,
    offset: 0,
  });
  if (!result) {
    return;
  }
  previewResult.value = result;
  previewContext.value = {
    mode: 'single',
    selectionKey: buildSelectionKey([finding.finding_id]),
    fingerprint: currentScanFingerprint.value,
  };
  selectedFindingIds.value = [finding.finding_id];
  applyResult.value = null;
  warningRead.value = false;
  backupCreated.value = false;
}

async function previewSelected(): Promise<void> {
  if (!selectedRepairableFindings.value.length) {
    return;
  }
  const assetIds = selectedRepairableFindings.value.map((finding) => finding.asset_id);
  const result = await consistencyStore.preview({
    asset_ids: assetIds,
    select_all: false,
    limit: assetIds.length,
    offset: 0,
  });
  if (!result) {
    return;
  }
  previewResult.value = result;
  previewContext.value = {
    mode: 'selected',
    selectionKey: currentSelectionKey.value,
    fingerprint: currentScanFingerprint.value,
  };
  applyResult.value = null;
  warningRead.value = false;
  backupCreated.value = false;
}

async function previewAll(): Promise<void> {
  const result = await consistencyStore.preview({
    asset_ids: [],
    select_all: true,
  });
  if (!result) {
    return;
  }
  previewResult.value = result;
  previewContext.value = {
    mode: 'all',
    selectionKey: '',
    fingerprint: currentScanFingerprint.value,
  };
  selectedFindingIds.value = result.selected_findings
    .filter((finding) => isRepairableFinding(finding))
    .map((finding) => finding.finding_id);
  applyResult.value = null;
  warningRead.value = false;
  backupCreated.value = false;
}

async function applyPreviewedRemoval(): Promise<void> {
  if (applyDisabled.value || !previewResult.value) {
    return;
  }
  const result = await consistencyStore.apply(previewResult.value.repair_run_id);
  if (!result) {
    return;
  }
  applyResult.value = result;
  clearPreviewState();
  reconcileSelections();
}

async function restoreSingleRestorePoint(restorePointId: string): Promise<void> {
  const result = await consistencyStore.restore({
    restore_point_ids: [restorePointId],
    select_all: false,
  });
  if (!result) {
    return;
  }
  restoreResult.value = result;
  selectedRestorePointIds.value = [];
  reconcileSelections();
}

async function restoreSelectedRestorePoints(): Promise<void> {
  if (!selectedRestorePointIds.value.length) {
    return;
  }
  const result = await consistencyStore.restore({
    restore_point_ids: selectedRestorePointIds.value,
    select_all: false,
  });
  if (!result) {
    return;
  }
  restoreResult.value = result;
  selectedRestorePointIds.value = [];
  reconcileSelections();
}

async function restoreAllRestorePoints(): Promise<void> {
  if (!consistencyStore.restorePoints.length) {
    return;
  }
  const result = await consistencyStore.restore({
    restore_point_ids: consistencyStore.restorePoints.map((item) => item.restore_point_id),
    select_all: true,
  });
  if (!result) {
    return;
  }
  restoreResult.value = result;
  selectedRestorePointIds.value = [];
  reconcileSelections();
}

function openDeleteDialog(restorePointIds: string[], selectAll: boolean): void {
  const normalizedIds = [...new Set(restorePointIds.filter(Boolean))];
  pendingDeleteRestorePointIds.value = normalizedIds;
  pendingDeleteSelectAll.value = selectAll;
  showDeleteDialog.value = selectAll || normalizedIds.length > 0;
}

function closeDeleteDialog(): void {
  showDeleteDialog.value = false;
  pendingDeleteRestorePointIds.value = [];
  pendingDeleteSelectAll.value = false;
}

async function confirmDeleteRestorePoints(): Promise<void> {
  if (!pendingDeleteSelectAll.value && !pendingDeleteRestorePointIds.value.length) {
    closeDeleteDialog();
    return;
  }
  const payload: MissingAssetRestorePointDeleteRequest = {
    restore_point_ids: pendingDeleteRestorePointIds.value,
    select_all: pendingDeleteSelectAll.value,
  };
  const result = await consistencyStore.deleteRestorePoints(payload);
  if (!result) {
    return;
  }
  deleteResult.value = result;
  selectedRestorePointIds.value = [];
  closeDeleteDialog();
  reconcileSelections();
}

onMounted(async () => {
  await consistencyStore.load();
  reconcileSelections();
});
</script>
