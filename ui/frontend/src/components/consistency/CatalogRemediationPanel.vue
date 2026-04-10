<template>
  <section class="panel catalog-remediation-panel">
    <div class="settings-section__header">
      <div>
        <h3>Catalog-backed remediation review</h3>
        <p>
          Review broken DB originals, zero-byte files, and `.fuse_hidden*`
          storage artifacts before any explicit apply step.
        </p>
      </div>
      <StatusTag :status="panelStatus" />
    </div>

    <p class="health-card__summary">
      {{
        consistencyStore.remediationScanResult?.summary ??
        "No remediation findings loaded yet."
      }}
    </p>
    <p
      v-if="consistencyStore.remediationError"
      class="runtime-blocking-message"
    >
      {{ consistencyStore.remediationError }}
    </p>

    <div class="runtime-actions">
      <button
        type="button"
        class="runtime-action runtime-action--secondary"
        :disabled="consistencyStore.isLoadingRemediation"
        @click="void refreshPanel()"
      >
        {{
          consistencyStore.isLoadingRemediation
            ? "Refreshing..."
            : "Refresh findings"
        }}
      </button>
    </div>

    <section class="catalog-remediation-section">
      <div class="settings-section__header">
        <div>
          <h4>Broken DB originals</h4>
          <p>
            `missing_confirmed` can use DB cleanup. `found_with_hash_match` can
            use explicit path correction. `found_elsewhere` stays inspect-only.
          </p>
        </div>
        <StatusTag :status="brokenDbStatus" />
      </div>

      <div class="runtime-actions">
        <button
          type="button"
          class="runtime-action"
          :disabled="
            !selectedBrokenCleanupEligible.length ||
            consistencyStore.isPreviewing
          "
          @click="void previewBrokenCleanupSelected()"
        >
          Preview cleanup selected ({{ selectedBrokenCleanupEligible.length }})
        </button>
        <button
          type="button"
          class="runtime-action"
          :disabled="
            !brokenCleanupEligible.length || consistencyStore.isPreviewing
          "
          @click="void previewBrokenCleanupAll()"
        >
          Preview cleanup all eligible ({{ brokenCleanupEligible.length }})
        </button>
        <button
          type="button"
          class="runtime-action"
          :disabled="
            !selectedBrokenFixEligible.length || consistencyStore.isPreviewing
          "
          @click="void previewBrokenFixSelected()"
        >
          Preview path fix selected ({{ selectedBrokenFixEligible.length }})
        </button>
        <button
          type="button"
          class="runtime-action"
          :disabled="!brokenFixEligible.length || consistencyStore.isPreviewing"
          @click="void previewBrokenFixAll()"
        >
          Preview path fix all eligible ({{ brokenFixEligible.length }})
        </button>
      </div>

      <div class="catalog-remediation-table-wrapper">
        <table class="catalog-table">
          <thead>
            <tr>
              <th>
                <input
                  type="checkbox"
                  :checked="allBrokenVisibleSelected"
                  :disabled="!brokenSelectableFindings.length"
                  @change="
                    toggleAllBroken(($event.target as HTMLInputElement).checked)
                  "
                />
              </th>
              <th>Asset</th>
              <th>Classification</th>
              <th>Expected path</th>
              <th>Found path</th>
              <th>Verification</th>
              <th>Action</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="finding in consistencyStore.brokenDbOriginals"
              :key="finding.finding_id"
            >
              <td>
                <input
                  type="checkbox"
                  :checked="selectedBrokenIds.includes(finding.asset_id)"
                  :disabled="!finding.action_eligible"
                  @change="
                    toggleBroken(
                      finding.asset_id,
                      ($event.target as HTMLInputElement).checked,
                    )
                  "
                />
              </td>
              <td>
                <strong>{{ finding.asset_name ?? finding.asset_id }}</strong>
                <small class="catalog-remediation-muted">{{
                  finding.asset_id
                }}</small>
              </td>
              <td>
                <span
                  :class="badgeClass(finding.classification)"
                  class="consistency-chip"
                >
                  {{ finding.classification }}
                </span>
                <small class="catalog-remediation-muted">{{
                  finding.message
                }}</small>
              </td>
              <td class="catalog-remediation-mono">
                {{ finding.expected_database_path }}
              </td>
              <td class="catalog-remediation-mono">
                {{ finding.found_absolute_path ?? "Not found" }}
              </td>
              <td>
                <span v-if="finding.checksum_match === true"
                  >Hash match verified</span
                >
                <span v-else-if="finding.checksum_match === false"
                  >Hash mismatch</span
                >
                <span v-else-if="finding.checksum_value"
                  >Checksum unavailable for safe auto-verify</span
                >
                <span v-else>Size/path only</span>
              </td>
              <td>{{ finding.action_reason }}</td>
            </tr>
            <tr v-if="!consistencyStore.brokenDbOriginals.length">
              <td colspan="7" class="consistency-empty-row">
                No broken DB originals found.
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <div class="catalog-remediation-preview">
        <p class="health-card__details">
          {{ brokenPreview?.summary ?? "No broken DB preview prepared." }}
        </p>
        <p
          v-if="consistencyStore.remediationPreviewError"
          class="runtime-blocking-message"
        >
          {{ consistencyStore.remediationPreviewError }}
        </p>
        <p v-if="brokenApplyResult" class="health-card__details">
          {{ brokenApplyResult.summary }}
        </p>
        <div class="catalog-remediation-confirm">
          <label
            ><input v-model="brokenWarningRead" type="checkbox" /> I reviewed
            the preview.</label
          >
          <label>
            <input v-model="brokenMutationRead" type="checkbox" />
            I understand this apply step mutates DB state.
          </label>
        </div>
        <button
          type="button"
          class="runtime-action"
          :disabled="brokenApplyDisabled"
          @click="void applyBrokenPreview()"
        >
          Apply broken DB preview
        </button>
      </div>
    </section>

    <section class="catalog-remediation-section">
      <div class="settings-section__header">
        <div>
          <h4>Zero-byte files</h4>
          <p>
            Upload orphans and broken derivatives can be deleted explicitly.
            Zero-byte uploads that are still referenced as originals remain
            blocked.
          </p>
        </div>
        <StatusTag :status="zeroByteStatus" />
      </div>

      <div class="runtime-actions">
        <button
          type="button"
          class="runtime-action"
          :disabled="
            !selectedZeroByteEligible.length || consistencyStore.isPreviewing
          "
          @click="void previewZeroByteSelected()"
        >
          Preview selected ({{ selectedZeroByteEligible.length }})
        </button>
        <button
          type="button"
          class="runtime-action"
          :disabled="
            !zeroByteEligibleFindings.length || consistencyStore.isPreviewing
          "
          @click="void previewZeroByteAll()"
        >
          Preview all eligible ({{ zeroByteEligibleFindings.length }})
        </button>
      </div>

      <div class="catalog-remediation-table-wrapper">
        <table class="catalog-table">
          <thead>
            <tr>
              <th>
                <input
                  type="checkbox"
                  :checked="allZeroByteVisibleSelected"
                  :disabled="!zeroByteEligibleFindings.length"
                  @change="
                    toggleAllZeroByte(
                      ($event.target as HTMLInputElement).checked,
                    )
                  "
                />
              </th>
              <th>File</th>
              <th>Classification</th>
              <th>Path</th>
              <th>Asset</th>
              <th>Action</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="finding in consistencyStore.zeroByteFindings"
              :key="finding.finding_id"
            >
              <td>
                <input
                  type="checkbox"
                  :checked="selectedZeroByteIds.includes(finding.finding_id)"
                  :disabled="!finding.action_eligible"
                  @change="
                    toggleZeroByte(
                      finding.finding_id,
                      ($event.target as HTMLInputElement).checked,
                    )
                  "
                />
              </td>
              <td>
                <strong>{{ finding.file_name }}</strong>
                <small class="catalog-remediation-muted">{{
                  finding.root_slug
                }}</small>
              </td>
              <td>
                <span
                  :class="badgeClass(finding.classification)"
                  class="consistency-chip"
                >
                  {{ finding.classification }}
                </span>
                <small class="catalog-remediation-muted">{{
                  finding.message
                }}</small>
              </td>
              <td class="catalog-remediation-mono">
                {{ finding.absolute_path }}
              </td>
              <td>
                {{ finding.asset_name ?? finding.asset_id ?? "No DB asset" }}
              </td>
              <td>{{ finding.action_reason }}</td>
            </tr>
            <tr v-if="!consistencyStore.zeroByteFindings.length">
              <td colspan="6" class="consistency-empty-row">
                No zero-byte remediation findings found.
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <div class="catalog-remediation-preview">
        <p class="health-card__details">
          {{ zeroBytePreview?.summary ?? "No zero-byte preview prepared." }}
        </p>
        <p v-if="zeroByteApplyResult" class="health-card__details">
          {{ zeroByteApplyResult.summary }}
        </p>
        <div class="catalog-remediation-confirm">
          <label
            ><input v-model="zeroByteWarningRead" type="checkbox" /> I reviewed
            the preview.</label
          >
          <label>
            <input v-model="zeroByteDeleteRead" type="checkbox" />
            I understand deletion is explicit and irreversible here.
          </label>
        </div>
        <button
          type="button"
          class="runtime-action"
          :disabled="zeroByteApplyDisabled"
          @click="void applyZeroBytePreview()"
        >
          Apply zero-byte preview
        </button>
      </div>
    </section>

    <section class="catalog-remediation-section">
      <div class="settings-section__header">
        <div>
          <h4>`.fuse_hidden*` storage orphans</h4>
          <p>
            `.immich` stays ignored. `blocked_in_use` stays informational. Only
            `deletable_orphan` rows become eligible for explicit deletion.
          </p>
        </div>
        <StatusTag :status="fuseStatus" />
      </div>

      <div class="runtime-actions">
        <button
          type="button"
          class="runtime-action"
          :disabled="
            !selectedFuseEligible.length || consistencyStore.isPreviewing
          "
          @click="void previewFuseSelected()"
        >
          Preview selected ({{ selectedFuseEligible.length }})
        </button>
        <button
          type="button"
          class="runtime-action"
          :disabled="
            !fuseEligibleFindings.length || consistencyStore.isPreviewing
          "
          @click="void previewFuseAll()"
        >
          Preview all eligible ({{ fuseEligibleFindings.length }})
        </button>
      </div>

      <div class="catalog-remediation-table-wrapper">
        <table class="catalog-table">
          <thead>
            <tr>
              <th>
                <input
                  type="checkbox"
                  :checked="allFuseVisibleSelected"
                  :disabled="!fuseEligibleFindings.length"
                  @change="
                    toggleAllFuse(($event.target as HTMLInputElement).checked)
                  "
                />
              </th>
              <th>File</th>
              <th>Classification</th>
              <th>Path</th>
              <th>Size</th>
              <th>Action</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="finding in consistencyStore.fuseHiddenOrphans"
              :key="finding.finding_id"
            >
              <td>
                <input
                  type="checkbox"
                  :checked="selectedFuseIds.includes(finding.finding_id)"
                  :disabled="!finding.action_eligible"
                  @change="
                    toggleFuse(
                      finding.finding_id,
                      ($event.target as HTMLInputElement).checked,
                    )
                  "
                />
              </td>
              <td>
                <strong>{{ finding.file_name }}</strong>
                <small class="catalog-remediation-muted">{{
                  finding.root_slug
                }}</small>
              </td>
              <td>
                <span
                  :class="badgeClass(finding.classification)"
                  class="consistency-chip"
                >
                  {{ finding.classification }}
                </span>
                <small class="catalog-remediation-muted">{{
                  finding.message
                }}</small>
              </td>
              <td class="catalog-remediation-mono">
                {{ finding.absolute_path }}
              </td>
              <td>{{ finding.size_bytes }}</td>
              <td>{{ finding.action_reason }}</td>
            </tr>
            <tr v-if="!consistencyStore.fuseHiddenOrphans.length">
              <td colspan="6" class="consistency-empty-row">
                No `.fuse_hidden*` orphan artifacts found.
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <div class="catalog-remediation-preview">
        <p class="health-card__details">
          {{ fusePreview?.summary ?? "No fuse-hidden preview prepared." }}
        </p>
        <p
          v-if="consistencyStore.remediationApplyError"
          class="runtime-blocking-message"
        >
          {{ consistencyStore.remediationApplyError }}
        </p>
        <p v-if="fuseApplyResult" class="health-card__details">
          {{ fuseApplyResult.summary }}
        </p>
        <div class="catalog-remediation-confirm">
          <label
            ><input v-model="fuseWarningRead" type="checkbox" /> I reviewed the
            preview.</label
          >
          <label>
            <input v-model="fuseDeleteRead" type="checkbox" />
            I understand deletion is irreversible here.
          </label>
        </div>
        <button
          type="button"
          class="runtime-action"
          :disabled="fuseApplyDisabled"
          @click="void applyFusePreview()"
        >
          Apply `.fuse_hidden*` preview
        </button>
      </div>
    </section>
  </section>
</template>

<script setup lang="ts">
import { computed, ref } from "vue";
import StatusTag from "@/components/common/StatusTag.vue";
import { useConsistencyStore } from "@/stores/consistency";
import type {
  CatalogRemediationApplyResponse,
  CatalogRemediationPreviewResponse,
} from "@/api/types/consistency";

type HealthTag = "ok" | "warning" | "error" | "unknown";

const consistencyStore = useConsistencyStore();
const selectedBrokenIds = ref<string[]>([]);
const selectedZeroByteIds = ref<string[]>([]);
const selectedFuseIds = ref<string[]>([]);
const brokenPreview = ref<CatalogRemediationPreviewResponse | null>(null);
const zeroBytePreview = ref<CatalogRemediationPreviewResponse | null>(null);
const fusePreview = ref<CatalogRemediationPreviewResponse | null>(null);
const brokenApplyResult = ref<CatalogRemediationApplyResponse | null>(null);
const zeroByteApplyResult = ref<CatalogRemediationApplyResponse | null>(null);
const fuseApplyResult = ref<CatalogRemediationApplyResponse | null>(null);
const brokenWarningRead = ref(false);
const brokenMutationRead = ref(false);
const zeroByteWarningRead = ref(false);
const zeroByteDeleteRead = ref(false);
const fuseWarningRead = ref(false);
const fuseDeleteRead = ref(false);

const brokenCleanupEligible = computed(() =>
  consistencyStore.brokenDbOriginals.filter((finding) =>
    finding.eligible_actions.includes("broken_db_cleanup"),
  ),
);
const brokenFixEligible = computed(() =>
  consistencyStore.brokenDbOriginals.filter((finding) =>
    finding.eligible_actions.includes("broken_db_path_fix"),
  ),
);
const brokenSelectableFindings = computed(() =>
  consistencyStore.brokenDbOriginals.filter(
    (finding) => finding.action_eligible,
  ),
);
const selectedBrokenCleanupEligible = computed(() =>
  brokenCleanupEligible.value.filter((finding) =>
    selectedBrokenIds.value.includes(finding.asset_id),
  ),
);
const selectedBrokenFixEligible = computed(() =>
  brokenFixEligible.value.filter((finding) =>
    selectedBrokenIds.value.includes(finding.asset_id),
  ),
);
const zeroByteEligibleFindings = computed(() =>
  consistencyStore.zeroByteFindings.filter(
    (finding) => finding.action_eligible,
  ),
);
const selectedZeroByteEligible = computed(() =>
  zeroByteEligibleFindings.value.filter((finding) =>
    selectedZeroByteIds.value.includes(finding.finding_id),
  ),
);
const fuseEligibleFindings = computed(() =>
  consistencyStore.fuseHiddenOrphans.filter(
    (finding) => finding.action_eligible,
  ),
);
const selectedFuseEligible = computed(() =>
  fuseEligibleFindings.value.filter((finding) =>
    selectedFuseIds.value.includes(finding.finding_id),
  ),
);
const allBrokenVisibleSelected = computed(
  () =>
    Boolean(brokenSelectableFindings.value.length) &&
    brokenSelectableFindings.value.every((finding) =>
      selectedBrokenIds.value.includes(finding.asset_id),
    ),
);
const allZeroByteVisibleSelected = computed(
  () =>
    Boolean(zeroByteEligibleFindings.value.length) &&
    selectedZeroByteEligible.value.length ===
      zeroByteEligibleFindings.value.length,
);
const allFuseVisibleSelected = computed(
  () =>
    Boolean(fuseEligibleFindings.value.length) &&
    selectedFuseEligible.value.length === fuseEligibleFindings.value.length,
);
const brokenApplyDisabled = computed(
  () =>
    !brokenPreview.value ||
    !brokenWarningRead.value ||
    !brokenMutationRead.value ||
    consistencyStore.isApplying,
);
const zeroByteApplyDisabled = computed(
  () =>
    !zeroBytePreview.value ||
    !zeroByteWarningRead.value ||
    !zeroByteDeleteRead.value ||
    consistencyStore.isApplying,
);
const fuseApplyDisabled = computed(
  () =>
    !fusePreview.value ||
    !fuseWarningRead.value ||
    !fuseDeleteRead.value ||
    consistencyStore.isApplying,
);
const panelStatus = computed<HealthTag>(() => {
  if (consistencyStore.remediationError) {
    return "error";
  }
  if (
    consistencyStore.brokenDbOriginals.length ||
    consistencyStore.zeroByteFindings.length ||
    consistencyStore.fuseHiddenOrphans.length
  ) {
    return "warning";
  }
  return "ok";
});
const brokenDbStatus = computed<HealthTag>(() =>
  consistencyStore.brokenDbOriginals.length ? "warning" : "ok",
);
const zeroByteStatus = computed<HealthTag>(() =>
  consistencyStore.zeroByteFindings.length ? "warning" : "ok",
);
const fuseStatus = computed<HealthTag>(() =>
  consistencyStore.fuseHiddenOrphans.length ? "warning" : "ok",
);

function badgeClass(value: string): string {
  return `consistency-chip--finding-${value}`;
}

function toggleBroken(assetId: string, checked: boolean): void {
  selectedBrokenIds.value = checked
    ? [...new Set([...selectedBrokenIds.value, assetId])]
    : selectedBrokenIds.value.filter((item) => item !== assetId);
}

function toggleZeroByte(findingId: string, checked: boolean): void {
  selectedZeroByteIds.value = checked
    ? [...new Set([...selectedZeroByteIds.value, findingId])]
    : selectedZeroByteIds.value.filter((item) => item !== findingId);
}

function toggleFuse(findingId: string, checked: boolean): void {
  selectedFuseIds.value = checked
    ? [...new Set([...selectedFuseIds.value, findingId])]
    : selectedFuseIds.value.filter((item) => item !== findingId);
}

function toggleAllBroken(checked: boolean): void {
  selectedBrokenIds.value = checked
    ? brokenSelectableFindings.value.map((item) => item.asset_id)
    : [];
}

function toggleAllZeroByte(checked: boolean): void {
  selectedZeroByteIds.value = checked
    ? zeroByteEligibleFindings.value.map((item) => item.finding_id)
    : [];
}

function toggleAllFuse(checked: boolean): void {
  selectedFuseIds.value = checked
    ? fuseEligibleFindings.value.map((item) => item.finding_id)
    : [];
}

async function refreshPanel(): Promise<void> {
  await consistencyStore.loadRemediation();
}

async function previewBrokenCleanupSelected(): Promise<void> {
  const result = await consistencyStore.previewBrokenDbOriginals({
    asset_ids: selectedBrokenCleanupEligible.value.map((item) => item.asset_id),
    select_all: false,
  });
  if (result) {
    brokenPreview.value = result;
    brokenApplyResult.value = null;
    brokenWarningRead.value = false;
    brokenMutationRead.value = false;
  }
}

async function previewBrokenCleanupAll(): Promise<void> {
  const result = await consistencyStore.previewBrokenDbOriginals({
    asset_ids: [],
    select_all: true,
  });
  if (result) {
    brokenPreview.value = result;
    brokenApplyResult.value = null;
    brokenWarningRead.value = false;
    brokenMutationRead.value = false;
  }
}

async function previewBrokenFixSelected(): Promise<void> {
  const result = await consistencyStore.previewBrokenDbPathFix({
    asset_ids: selectedBrokenFixEligible.value.map((item) => item.asset_id),
    select_all: false,
  });
  if (result) {
    brokenPreview.value = result;
    brokenApplyResult.value = null;
    brokenWarningRead.value = false;
    brokenMutationRead.value = false;
  }
}

async function previewBrokenFixAll(): Promise<void> {
  const result = await consistencyStore.previewBrokenDbPathFix({
    asset_ids: [],
    select_all: true,
  });
  if (result) {
    brokenPreview.value = result;
    brokenApplyResult.value = null;
    brokenWarningRead.value = false;
    brokenMutationRead.value = false;
  }
}

async function applyBrokenPreview(): Promise<void> {
  if (!brokenPreview.value) {
    return;
  }
  const result = await consistencyStore.applyRemediation(
    brokenPreview.value.repair_run_id,
  );
  if (result) {
    brokenApplyResult.value = result;
    brokenPreview.value = null;
  }
}

async function previewZeroByteSelected(): Promise<void> {
  const result = await consistencyStore.previewZeroByte({
    finding_ids: selectedZeroByteEligible.value.map((item) => item.finding_id),
    select_all: false,
  });
  if (result) {
    zeroBytePreview.value = result;
    zeroByteApplyResult.value = null;
    zeroByteWarningRead.value = false;
    zeroByteDeleteRead.value = false;
  }
}

async function previewZeroByteAll(): Promise<void> {
  const result = await consistencyStore.previewZeroByte({
    finding_ids: [],
    select_all: true,
  });
  if (result) {
    zeroBytePreview.value = result;
    zeroByteApplyResult.value = null;
    zeroByteWarningRead.value = false;
    zeroByteDeleteRead.value = false;
  }
}

async function applyZeroBytePreview(): Promise<void> {
  if (!zeroBytePreview.value) {
    return;
  }
  const result = await consistencyStore.applyRemediation(
    zeroBytePreview.value.repair_run_id,
  );
  if (result) {
    zeroByteApplyResult.value = result;
    zeroBytePreview.value = null;
  }
}

async function previewFuseSelected(): Promise<void> {
  const result = await consistencyStore.previewFuseHidden({
    finding_ids: selectedFuseEligible.value.map((item) => item.finding_id),
    select_all: false,
  });
  if (result) {
    fusePreview.value = result;
    fuseApplyResult.value = null;
    fuseWarningRead.value = false;
    fuseDeleteRead.value = false;
  }
}

async function previewFuseAll(): Promise<void> {
  const result = await consistencyStore.previewFuseHidden({
    finding_ids: [],
    select_all: true,
  });
  if (result) {
    fusePreview.value = result;
    fuseApplyResult.value = null;
    fuseWarningRead.value = false;
    fuseDeleteRead.value = false;
  }
}

async function applyFusePreview(): Promise<void> {
  if (!fusePreview.value) {
    return;
  }
  const result = await consistencyStore.applyRemediation(
    fusePreview.value.repair_run_id,
  );
  if (result) {
    fuseApplyResult.value = result;
    fusePreview.value = null;
  }
}
</script>

<style scoped>
.catalog-remediation-panel,
.catalog-remediation-section,
.catalog-remediation-preview {
  display: grid;
  gap: 1rem;
}

.catalog-remediation-table-wrapper {
  overflow-x: auto;
}

.catalog-remediation-confirm {
  display: grid;
  gap: 0.5rem;
}

.catalog-remediation-muted {
  display: block;
  color: #5c6b77;
}

.catalog-remediation-mono {
  font-family: "SFMono-Regular", Consolas, "Liberation Mono", monospace;
  word-break: break-all;
}
</style>
