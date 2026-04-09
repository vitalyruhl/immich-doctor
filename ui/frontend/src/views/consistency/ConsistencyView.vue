<template>
  <section class="page">
    <PageHeader
      eyebrow="Consistency"
      title="Consistency"
      summary="Review cached storage-vs-database mismatches, orphan derivatives, and the original missing-asset repair workflow."
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
    <LoadingState
      v-else-if="consistencyStore.isWaitingOnCatalog && !hasAnyData"
      :title="consistencyStore.catalogReadinessTitle"
      :message="consistencyStore.catalogReadinessMessage"
    />
    <ErrorState
      v-else-if="initialLoadError && !hasAnyData"
      title="Consistency data unavailable"
      :message="initialLoadError"
    />

    <template v-else>
      <CatalogConsistencyPanel />

      <section class="health-grid">
        <article class="panel">
          <div class="health-card__header">
            <h3>Scan summary</h3>
            <StatusTag :status="scanStatusTag" />
          </div>
          <p class="health-card__summary">{{ scanSummaryLabel }}</p>
          <p class="health-card__details">
            {{ scanSummaryDetails }}
          </p>
          <dl class="runtime-detail__grid">
            <dt>Scan tables</dt>
            <dd>{{ scanTablesLabel }}</dd>
            <dt>Path field</dt>
            <dd>{{ scanPathFieldLabel }}</dd>
            <dt>Restore tables</dt>
            <dd>{{ repairTablesLabel }}</dd>
            <dt>Scan blockers</dt>
            <dd>{{ scanBlockerSummaryLabel }}</dd>
            <dt>Covered dependency tables</dt>
            <dd>{{ coveredDependencyTablesLabel }}</dd>
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
              :disabled="consistencyStore.isScanning || consistencyStore.isWaitingOnCatalog"
              @click="void refreshScan()"
            >
              {{ consistencyStore.isScanning ? 'Rescanning' : 'Rescan findings' }}
            </button>
            <button
              class="runtime-action"
              type="button"
              :disabled="consistencyStore.isWaitingOnCatalog || !selectedRepairableFindings.length || consistencyStore.isPreviewing"
              @click="void previewSelected()"
            >
              Preview selected ({{ selectedRepairableFindings.length }})
            </button>
            <button
              class="runtime-action"
              type="button"
              :disabled="consistencyStore.isWaitingOnCatalog || !consistencyStore.findings.length || consistencyStore.isPreviewing"
              @click="void previewAll()"
            >
              Preview all ({{ consistencyStore.findings.length }})
            </button>
          </div>
        </div>

        <RiskNotice
          v-if="consistencyStore.isWaitingOnCatalog"
          :title="consistencyStore.catalogReadinessTitle"
          :message="consistencyStore.catalogReadinessMessage"
        />

        <section v-if="!consistencyStore.isWaitingOnCatalog" class="consistency-filter-bar">
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

        <section
          v-if="consistencyStore.findings.length && !consistencyStore.isWaitingOnCatalog"
          class="consistency-scan-summary"
        >
          <article class="consistency-scan-summary__item">
            <span>Blocked findings</span>
            <strong>{{ blockedForRepairCount }}</strong>
            <small>{{ scanBlockerSummaryLabel }}</small>
          </article>
          <article class="consistency-scan-summary__item">
            <span>Unsupported tables detected</span>
            <strong>{{ unsupportedDependencyTables.length }}</strong>
            <small>{{ unsupportedDependencyTablesLabel }}</small>
          </article>
          <article class="consistency-scan-summary__item">
            <span>Covered repair tables</span>
            <strong>{{ coveredDependencyTables.length }}</strong>
            <small>{{ coveredDependencyTablesLabel }}</small>
          </article>
        </section>

        <ErrorState
          v-if="consistencyStore.scanError && !consistencyStore.isWaitingOnCatalog"
          title="Scan findings unavailable"
          :message="consistencyStore.scanError"
        />
        <div v-else-if="consistencyStore.isWaitingOnCatalog" class="runtime-blocking-message">
          {{ consistencyStore.catalogReadinessMessage }}
        </div>
        <div v-else class="consistency-table-wrap">
          <table class="consistency-table">
            <thead>
              <tr>
                <th class="consistency-table__checkbox-cell">
                  <input
                    type="checkbox"
                    :checked="allVisibleFindingsSelected"
                    :indeterminate="someVisibleFindingsSelected"
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
              <template v-for="finding in sortedFindings" :key="finding.finding_id">
                <tr :class="{ 'consistency-table__row--expanded': isFindingExpanded(finding.finding_id) }">
                  <td class="consistency-table__checkbox-cell">
                    <input
                      type="checkbox"
                      :checked="selectedFindingSet.has(finding.finding_id)"
                      :disabled="!isRepairableFinding(finding)"
                      :aria-label="`Select finding ${finding.finding_id}`"
                      @change="toggleFindingSelection(finding.finding_id, ($event.target as HTMLInputElement).checked)"
                    />
                  </td>
                  <td class="consistency-table__cell consistency-table__cell--mono">
                    {{ finding.asset_id }}
                  </td>
                  <td class="consistency-table__cell">{{ finding.owner_id ?? 'Unavailable' }}</td>
                  <td class="consistency-table__cell">{{ finding.asset_type }}</td>
                  <td class="consistency-table__cell consistency-table__cell--path">
                    <strong
                      class="consistency-table__path-line"
                      :title="finding.logical_path"
                    >
                      {{ finding.logical_path || 'Unavailable' }}
                    </strong>
                    <small
                      class="consistency-table__path-line consistency-table__path-line--secondary"
                      :title="finding.resolved_physical_path"
                    >
                      {{ finding.resolved_physical_path || 'Unavailable' }}
                    </small>
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
                  <td class="consistency-table__cell">
                    <div class="consistency-table__blocker-cell">
                      <span
                        :class="findingBlockerChipClass(finding)"
                        class="consistency-chip"
                      >
                        {{ findingBlockerBadgeLabel(finding) }}
                      </span>
                      <small>{{ findingBlockerSummary(finding) }}</small>
                    </div>
                  </td>
                  <td class="consistency-table__cell">{{ formatDate(finding.scan_timestamp) }}</td>
                  <td class="consistency-table__cell">
                    <div class="runtime-actions consistency-row-actions">
                      <button
                        type="button"
                        class="runtime-action runtime-action--secondary"
                        @click="toggleFindingExpansion(finding.finding_id)"
                      >
                        {{ isFindingExpanded(finding.finding_id) ? 'Hide details' : 'View details' }}
                      </button>
                      <button
                        type="button"
                        class="runtime-action runtime-action--secondary"
                        :disabled="!isRepairableFinding(finding) || consistencyStore.isPreviewing"
                        @click="void previewSingle(finding)"
                      >
                        Preview single
                      </button>
                    </div>
                  </td>
                </tr>
                <tr v-if="isFindingExpanded(finding.finding_id)" class="consistency-table__detail-row">
                  <td :colspan="findingColumns.length + 3">
                    <section class="consistency-finding-detail">
                      <div class="consistency-finding-detail__header">
                        <div>
                          <h4>{{ finding.asset_id }}</h4>
                          <p>{{ finding.message }}</p>
                        </div>
                        <div class="consistency-finding-detail__chips">
                          <span :class="findingStatusClass(finding.status)" class="consistency-chip">
                            {{ formatFindingStatus(finding.status) }}
                          </span>
                          <span :class="readinessStatusClass(finding.repair_readiness)" class="consistency-chip">
                            {{ finding.repair_readiness }}
                          </span>
                        </div>
                      </div>
                      <dl class="consistency-finding-detail__grid">
                        <dt>Owner / user</dt>
                        <dd>{{ finding.owner_id ?? 'Unavailable' }}</dd>
                        <dt>Asset type</dt>
                        <dd>{{ finding.asset_type }}</dd>
                        <dt>Logical path</dt>
                        <dd class="consistency-table__cell--mono">{{ finding.logical_path || 'Unavailable' }}</dd>
                        <dt>Resolved physical path</dt>
                        <dd class="consistency-table__cell--mono">
                          {{ finding.resolved_physical_path || 'Unavailable' }}
                        </dd>
                        <dt>Created</dt>
                        <dd>{{ formatDate(finding.created_at) }}</dd>
                        <dt>Updated</dt>
                        <dd>{{ formatDate(finding.updated_at) }}</dd>
                        <dt>Scan timestamp</dt>
                        <dd>{{ formatDate(finding.scan_timestamp) }}</dd>
                      </dl>
                      <section class="consistency-finding-detail__blockers">
                        <div class="consistency-finding-detail__section-header">
                          <h5>Repair blockers</h5>
                          <small>
                            {{
                              normalizedFindingBlockers(finding).length
                                ? `${normalizedFindingBlockers(finding).length} blocker(s)`
                                : 'No active blockers'
                            }}
                          </small>
                        </div>
                        <p
                          v-if="!normalizedFindingBlockers(finding).length"
                          class="consistency-finding-detail__empty"
                        >
                          This finding is ready for preview and apply.
                        </p>
                        <article
                          v-for="blocker in normalizedFindingBlockers(finding)"
                          :key="`${finding.finding_id}:${blocker.blocker_code}:${blocker.summary}`"
                          class="consistency-blocker-card"
                        >
                          <div class="consistency-blocker-card__header">
                            <strong>{{ blocker.summary }}</strong>
                            <span class="consistency-chip consistency-chip--blocked-detail">
                              {{ formatBlockingSeverity(blocker.blocking_severity) }}
                            </span>
                          </div>
                          <p>{{ blockerReason(blocker) }}</p>
                          <dl class="consistency-blocker-card__grid">
                            <dt>Blocker code</dt>
                            <dd class="consistency-table__cell--mono">{{ blocker.blocker_code }}</dd>
                            <dt>Type</dt>
                            <dd>{{ blocker.blocker_type }}</dd>
                            <dt>Repairable</dt>
                            <dd>{{ blocker.is_repairable ? 'Yes' : 'No' }}</dd>
                          </dl>
                          <div v-if="blocker.affected_tables.length" class="consistency-blocker-card__section">
                            <h6>Unsupported tables</h6>
                            <ul class="consistency-blocker-card__list">
                              <li v-for="table in blocker.affected_tables" :key="table">
                                <code>{{ table }}</code>
                              </li>
                            </ul>
                          </div>
                          <div
                            v-if="blocker.repair_covered_tables.length"
                            class="consistency-blocker-card__section"
                          >
                            <h6>Repair currently covers</h6>
                            <ul class="consistency-blocker-card__list">
                              <li v-for="table in blocker.repair_covered_tables" :key="table">
                                <code>{{ table }}</code>
                              </li>
                            </ul>
                          </div>
                        </article>
                      </section>
                    </section>
                  </td>
                </tr>
              </template>
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
import CatalogConsistencyPanel from '@/components/consistency/CatalogConsistencyPanel.vue';
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
  MissingAssetRepairBlocker,
  MissingAssetReferenceFinding,
  MissingAssetReferenceStatus,
  MissingAssetRestorePoint,
  MissingAssetRestorePointDeleteRequest,
  MissingAssetRestorePointDeleteResponse,
  MissingAssetRestoreResponse,
  RepairReadinessStatus,
  MissingAssetSupportedScopeMetadata,
} from '@/api/types/consistency';

type FindingSortField =
  | 'asset_id'
  | 'owner_id'
  | 'asset_type'
  | 'logical_path'
  | 'status'
  | 'scan_timestamp'
  | 'repair_readiness';

interface FindingColumn {
  key: FindingSortField;
  label: string;
}

const findingColumns: FindingColumn[] = [
  { key: 'asset_id', label: 'Asset id' },
  { key: 'owner_id', label: 'Owner / user' },
  { key: 'asset_type', label: 'Asset type' },
  { key: 'logical_path', label: 'Paths' },
  { key: 'status', label: 'Status' },
  { key: 'repair_readiness', label: 'Readiness' },
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
const expandedFindingIds = ref<string[]>([]);
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
      ...normalizedFindingBlockers(finding).flatMap((blocker) => [
        blocker.blocker_code,
        blocker.blocker_type,
        blocker.summary,
        blockerReason(blocker),
        ...blocker.affected_tables,
        ...blocker.repair_covered_tables,
      ]),
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
      case 'status':
        result = compareStrings(left.status, right.status);
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
const someVisibleFindingsSelected = computed(
  () =>
    visibleRepairableFindingIds.value.length > 0 &&
    visibleRepairableFindingIds.value.some((findingId) => selectedFindingSet.value.has(findingId)) &&
    !allVisibleFindingsSelected.value,
);
const allRestorePointsSelected = computed(
  () =>
    consistencyStore.restorePoints.length > 0 &&
    consistencyStore.restorePoints.every((item) => selectedRestorePointSet.value.has(item.restore_point_id)),
);
const hasAnyData = computed(
  () => consistencyStore.findings.length > 0 || consistencyStore.restorePoints.length > 0,
);
const initialLoadError = computed(() => {
  if (consistencyStore.isWaitingOnCatalog) {
    return consistencyStore.restorePointsError ?? consistencyStore.catalogJobError ?? null;
  }
  return (
    consistencyStore.catalogJobError
    ?? consistencyStore.scanError
    ?? consistencyStore.restorePointsError
    ?? null
  );
});
const missingOnDiskCount = computed(
  () => consistencyStore.findings.filter((finding) => finding.status === 'missing_on_disk').length,
);
const readyForRepairCount = computed(
  () => consistencyStore.findings.filter((finding) => finding.repair_readiness === 'ready').length,
);
const blockedForRepairCount = computed(
  () => consistencyStore.findings.filter((finding) => finding.repair_readiness === 'blocked').length,
);
const scanStatusTag = computed<HealthState>(() => {
  if (consistencyStore.isWaitingOnCatalog) {
    return 'warning';
  }
  return toHealthState(consistencyStore.scanError, consistencyStore.scanResult);
});
const scanSummaryLabel = computed(() => {
  if (consistencyStore.isWaitingOnCatalog) {
    return consistencyStore.catalogReadinessTitle;
  }
  return `${consistencyStore.findings.length} findings loaded`;
});
const scanSummaryDetails = computed(() => {
  if (consistencyStore.isWaitingOnCatalog) {
    return consistencyStore.catalogReadinessMessage;
  }
  return consistencyStore.scanResult?.summary ?? 'No scan has been run yet.';
});
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
const supportedScope = computed<MissingAssetSupportedScopeMetadata | null>(() => {
  const scope = consistencyStore.scanResult?.metadata?.supportedScope;
  return scope && typeof scope === 'object' ? (scope as MissingAssetSupportedScopeMetadata) : null;
});
const scanTablesLabel = computed(() => formatListValue(supportedScope.value?.scanTables));
const scanPathFieldLabel = computed(() => formatValue(supportedScope.value?.scanPathField));
const repairTablesLabel = computed(() => formatListValue(supportedScope.value?.repairRestoreTables));
const scanBlockers = computed<MissingAssetRepairBlocker[]>(() => {
  const blockers = supportedScope.value?.scanBlockers;
  return Array.isArray(blockers) ? blockers : [];
});
const coveredDependencyTables = computed(() => {
  const tables = supportedScope.value?.repairCoveredDependencyTables;
  if (!Array.isArray(tables)) {
    return [];
  }
  return tables.filter(
    (table): table is string => typeof table === 'string' && table.trim().length > 0,
  );
});
const unsupportedDependencyTables = computed(() =>
  Array.from(
    new Set(
      scanBlockers.value.flatMap((blocker) =>
        blocker.blocker_code === 'unsupported_dependency_tables' ? blocker.affected_tables : [],
      ),
    ),
  ).sort(),
);
const scanBlockerSummaryLabel = computed(() => {
  if (!scanBlockers.value.length) {
    return 'None';
  }
  if (
    scanBlockers.value.length === 1 &&
    scanBlockers.value[0]?.blocker_code === 'unsupported_dependency_tables'
  ) {
    return `Unsupported dependency tables (${scanBlockers.value[0].affected_tables.length})`;
  }
  return scanBlockers.value.map((blocker) => blocker.summary).join(', ');
});
const unsupportedDependencyTablesLabel = computed(() =>
  formatCompactList(unsupportedDependencyTables.value, 'No unsupported tables'),
);
const coveredDependencyTablesLabel = computed(() =>
  formatCompactList(coveredDependencyTables.value, 'Unavailable'),
);
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

function formatCompactList(items: string[], emptyValue = 'Unavailable', maxItems = 3): string {
  if (!items.length) {
    return emptyValue;
  }
  if (items.length <= maxItems) {
    return items.join(', ');
  }
  return `${items.slice(0, maxItems).join(', ')}, +${items.length - maxItems} more`;
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

function normalizeRepairBlocker(blocker: MissingAssetRepairBlocker): MissingAssetRepairBlocker {
  return {
    blocker_code: blocker.blocker_code,
    blocker_type: blocker.blocker_type,
    summary: blocker.summary,
    details: blocker.details ?? {},
    affected_tables: blocker.affected_tables ?? [],
    repair_covered_tables: blocker.repair_covered_tables ?? [],
    blocking_severity: blocker.blocking_severity ?? 'error',
    is_repairable: blocker.is_repairable ?? false,
  };
}

function normalizedFindingBlockers(finding: MissingAssetReferenceFinding): MissingAssetRepairBlocker[] {
  if (Array.isArray(finding.repair_blocker_details) && finding.repair_blocker_details.length) {
    return finding.repair_blocker_details.map(normalizeRepairBlocker);
  }
  return (finding.repair_blockers ?? []).map((summary, index) =>
    normalizeRepairBlocker({
      blocker_code: `legacy_blocker_${index + 1}`,
      blocker_type: 'scope',
      summary,
      details: {},
      affected_tables: [],
      repair_covered_tables: [],
      blocking_severity: 'error',
      is_repairable: false,
    }),
  );
}

function findingBlockerBadgeLabel(finding: MissingAssetReferenceFinding): string {
  return normalizedFindingBlockers(finding).length ? 'Blocked' : 'Ready';
}

function findingBlockerSummary(finding: MissingAssetReferenceFinding): string {
  const blockers = normalizedFindingBlockers(finding);
  if (!blockers.length) {
    return 'No active blockers';
  }
  const unsupportedTablesBlocker = blockers.find(
    (blocker) => blocker.blocker_code === 'unsupported_dependency_tables',
  );
  if (unsupportedTablesBlocker) {
    return `unsupported dependency tables (${unsupportedTablesBlocker.affected_tables.length})`;
  }
  if (blockers.length === 1) {
    return blockers[0].summary;
  }
  return `${blockers.length} blocker reasons`;
}

function findingBlockerChipClass(finding: MissingAssetReferenceFinding): string {
  return normalizedFindingBlockers(finding).length
    ? 'consistency-chip--blocked'
    : 'consistency-chip--ready';
}

function blockerReason(blocker: MissingAssetRepairBlocker): string {
  const reason = blocker.details?.reason;
  return typeof reason === 'string' && reason.trim()
    ? reason
    : 'Repair remains blocked until this blocker is resolved.';
}

function formatBlockingSeverity(severity: MissingAssetRepairBlocker['blocking_severity']): string {
  return severity.replace(/_/g, ' ');
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

function toggleFindingSelection(findingId: string, checked: boolean): void {
  const finding = consistencyStore.findings.find((item) => item.finding_id === findingId);
  if (!finding || !isRepairableFinding(finding)) {
    return;
  }
  const nextSelection = new Set(selectedFindingIds.value);
  if (checked) {
    nextSelection.add(findingId);
  } else {
    nextSelection.delete(findingId);
  }
  selectedFindingIds.value = [...nextSelection];
}

function isFindingExpanded(findingId: string): boolean {
  return expandedFindingIds.value.includes(findingId);
}

function toggleFindingExpansion(findingId: string): void {
  expandedFindingIds.value = isFindingExpanded(findingId)
    ? expandedFindingIds.value.filter((item) => item !== findingId)
    : [...expandedFindingIds.value, findingId];
}

function toggleAllVisibleFindings(checked: boolean): void {
  const visibleIds = visibleRepairableFindingIds.value;
  const nextSelection = new Set(selectedFindingIds.value);
  for (const findingId of visibleIds) {
    if (checked) {
      nextSelection.add(findingId);
    } else {
      nextSelection.delete(findingId);
    }
  }
  selectedFindingIds.value = [...nextSelection];
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
  expandedFindingIds.value = expandedFindingIds.value.filter((findingId) =>
    consistencyStore.findings.some((finding) => finding.finding_id === findingId),
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
  if (consistencyStore.isWaitingOnCatalog) {
    await consistencyStore.loadCatalogJob();
    return;
  }
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
