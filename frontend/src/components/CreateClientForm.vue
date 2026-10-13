<script setup lang="ts">
/* eslint-disable vue/attributes-order, vue/multiline-html-element-content-newline */
import { nextTick, reactive, ref, watch } from "vue";
import type { CreateClientInput } from "../api/dto";

const props = withDefaults(
  defineProps<{
    submitting: boolean;
    serverErrors: Record<string, string>;
    mode?: "create" | "edit";
    initialValue?: CreateClientInput | null;
  }>(),
  { mode: "create", initialValue: null },
);
const emit = defineEmits<{
  submit: [input: CreateClientInput];
  cancel: [];
  dirty: [];
  change: [input: CreateClientInput];
}>();
const form = reactive({
  standard_name: "",
  short_name: "",
  industry_code: "",
  province: "",
  city: "",
  district: "",
  address: "",
  contact_phone: "",
  contact_wechat: "",
  business_hours: "",
  service_radius: "",
  cooperation_started_on: "",
  notes: "",
});
const localErrors = ref<Record<string, string>>({});
const standardNameInput = ref<HTMLInputElement | null>(null);
const summaryRef = ref<HTMLElement | null>(null);
const submittingValidation = ref(false);
const required: (keyof typeof form)[] = [
  "standard_name",
  "industry_code",
  "province",
  "city",
  "district",
  "address",
  "cooperation_started_on",
];
const label: Record<string, string> = {
  standard_name: "企业名称",
  industry_code: "行业代码",
  province: "省份",
  city: "城市",
  district: "区县",
  address: "详细地址",
  cooperation_started_on: "合作开始日期",
};
const errorFor = (field: string): string =>
  localErrors.value[field] ?? props.serverErrors[field] ?? "";
const allErrors = () => ({ ...props.serverErrors, ...localErrors.value });
const nullable = (value: string): string | null => value.trim() || null;
const normalizeForm = (): CreateClientInput => ({
  standard_name: form.standard_name.trim(),
  short_name: nullable(form.short_name),
  industry_code: form.industry_code.trim(),
  province: form.province.trim(),
  city: form.city.trim(),
  district: form.district.trim(),
  address: form.address.trim(),
  contact_phone: nullable(form.contact_phone),
  contact_wechat: nullable(form.contact_wechat),
  business_hours: nullable(form.business_hours),
  service_radius: nullable(form.service_radius),
  cooperation_started_on: form.cooperation_started_on,
  notes: nullable(form.notes),
});
const populateForm = (value: CreateClientInput | null): void => {
  const source = value ?? {
    standard_name: "",
    short_name: null,
    industry_code: "",
    province: "",
    city: "",
    district: "",
    address: "",
    contact_phone: null,
    contact_wechat: null,
    business_hours: null,
    service_radius: null,
    cooperation_started_on: "",
    notes: null,
  };
  Object.assign(
    form,
    Object.fromEntries(
      Object.entries(source).map(([key, fieldValue]) => [
        key,
        fieldValue ?? "",
      ]),
    ),
  );
  localErrors.value = {};
  submittingValidation.value = false;
};
watch(
  () => props.initialValue,
  (value) => populateForm(value),
  { immediate: true },
);
watch(
  () => props.serverErrors,
  (next) => {
    if (Object.keys(next).length)
      void nextTick(() => summaryRef.value?.focus());
  },
);
const handleInput = (): void => {
  submittingValidation.value = false;
  emit("dirty");
  emit("change", normalizeForm());
};
const submit = (): void => {
  localErrors.value = Object.fromEntries(
    required
      .filter((field) => !form[field].trim())
      .map((field) => [field, `请填写${label[field]}`]),
  );
  if (Object.keys(localErrors.value).length) {
    void nextTick(() => standardNameInput.value?.focus());
    return;
  }
  submittingValidation.value = true;
  void nextTick(() => summaryRef.value?.focus());
  emit("submit", normalizeForm());
};
</script>

<template>
  <form
    class="client-form"
    novalidate
    @input="handleInput"
    @submit.prevent="submit"
  >
    <p class="form-help">
      {{
        mode === "edit"
          ? "修改会同步更新企业档案，并用于后续 GEO 诊断与内容生成。"
          : "带 * 的字段为建档必填项。"
      }}
    </p>
    <div
      v-if="submittingValidation || Object.keys(allErrors()).length"
      ref="summaryRef"
      class="form-alert"
      role="alert"
      tabindex="-1"
    >
      {{
        Object.keys(allErrors()).length
          ? "请修正表单中的错误。"
          : "正在校验表单。"
      }}
    </div>
    <div class="form-grid">
      <label class="field"
        ><span>企业名称</span
        ><input
          ref="standardNameInput"
          v-model="form.standard_name"
          aria-label="企业名称"
          aria-required="true"
          required
          :aria-invalid="
            submittingValidation || Boolean(errorFor('standard_name'))
          "
          :aria-describedby="
            submittingValidation || errorFor('standard_name')
              ? 'standard-name-error'
              : undefined
          "
        /><small
          v-if="errorFor('standard_name')"
          id="standard-name-error"
          class="field-error"
          >{{ errorFor("standard_name") }}</small
        ></label
      >
      <label class="field"
        ><span>企业简称</span><input v-model="form.short_name"
      /></label>
      <label class="field"
        ><span>行业代码</span
        ><input
          v-model="form.industry_code"
          aria-label="行业代码"
          aria-required="true"
          required
          :aria-invalid="
            submittingValidation || Boolean(errorFor('industry_code'))
          "
          :aria-describedby="
            submittingValidation || errorFor('industry_code')
              ? 'industry-code-error'
              : undefined
          "
        /><small
          id="industry-code-error"
          v-if="errorFor('industry_code')"
          class="field-error"
          >{{ errorFor("industry_code") }}</small
        ></label
      >
      <label class="field"
        ><span>合作开始日期</span
        ><input
          v-model="form.cooperation_started_on"
          aria-label="合作开始日期"
          aria-required="true"
          type="date"
          required
          :aria-invalid="
            submittingValidation || Boolean(errorFor('cooperation_started_on'))
          "
          :aria-describedby="
            submittingValidation || errorFor('cooperation_started_on')
              ? 'cooperation-started-on-error'
              : undefined
          "
        /><small
          id="cooperation-started-on-error"
          v-if="errorFor('cooperation_started_on')"
          class="field-error"
          >{{ errorFor("cooperation_started_on") }}</small
        ></label
      >
      <label class="field"
        ><span>省份</span
        ><input
          v-model="form.province"
          aria-label="省份"
          aria-required="true"
          required
          :aria-invalid="submittingValidation || Boolean(errorFor('province'))"
          :aria-describedby="
            submittingValidation || errorFor('province')
              ? 'province-error'
              : undefined
          "
        /><small
          id="province-error"
          v-if="errorFor('province')"
          class="field-error"
          >{{ errorFor("province") }}</small
        ></label
      >
      <label class="field"
        ><span>城市</span
        ><input
          v-model="form.city"
          aria-label="城市"
          aria-required="true"
          required
          :aria-invalid="submittingValidation || Boolean(errorFor('city'))"
          :aria-describedby="
            submittingValidation || errorFor('city') ? 'city-error' : undefined
          "
        /><small id="city-error" v-if="errorFor('city')" class="field-error">{{
          errorFor("city")
        }}</small></label
      >
      <label class="field"
        ><span>区县</span
        ><input
          v-model="form.district"
          aria-label="区县"
          aria-required="true"
          required
          :aria-invalid="submittingValidation || Boolean(errorFor('district'))"
          :aria-describedby="
            submittingValidation || errorFor('district')
              ? 'district-error'
              : undefined
          "
        /><small
          id="district-error"
          v-if="errorFor('district')"
          class="field-error"
          >{{ errorFor("district") }}</small
        ></label
      >
      <label class="field"
        ><span>详细地址</span
        ><input
          v-model="form.address"
          aria-label="详细地址"
          aria-required="true"
          required
          :aria-invalid="submittingValidation || Boolean(errorFor('address'))"
          :aria-describedby="
            submittingValidation || errorFor('address')
              ? 'address-error'
              : undefined
          "
        /><small
          id="address-error"
          v-if="errorFor('address')"
          class="field-error"
          >{{ errorFor("address") }}</small
        ></label
      >
      <label class="field"
        ><span>联系电话</span><input v-model="form.contact_phone" /></label
      ><label class="field"
        ><span>联系微信</span><input v-model="form.contact_wechat"
      /></label>
      <label class="field"
        ><span>营业时间</span><input v-model="form.business_hours" /></label
      ><label class="field"
        ><span>服务范围</span><input v-model="form.service_radius"
      /></label>
      <label class="field full-field"
        ><span>备注</span><textarea v-model="form.notes" rows="2" />
      </label>
    </div>
    <footer class="modal-actions">
      <button
        class="button"
        type="button"
        :disabled="props.submitting"
        @click="emit('cancel')"
      >
        取消</button
      ><button
        class="button primary"
        type="submit"
        :disabled="props.submitting"
      >
        {{
          props.submitting
            ? mode === "edit"
              ? "正在保存…"
              : "正在创建…"
            : mode === "edit"
              ? "保存客户资料"
              : "创建客户"
        }}
      </button>
    </footer>
  </form>
</template>
