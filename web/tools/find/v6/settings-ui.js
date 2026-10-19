/** V6 advanced controls and the immutable configuration attached to a result. */
import { $, state } from "../../../shared.js";
import { V6_SETTINGS, V6_DEFAULT_CONFIG, resolveV6Config, isCustomV6Config } from "./config.js";

export function validV6Settings() {
  return [...$("#findV6SettingsInputs").querySelectorAll("input")].every(input => input.validity.valid && input.value !== "");
}
export function bindV6Settings(onChange) {
  const container = $("#findV6SettingsInputs");
  for (const field of V6_SETTINGS) {
    const label = document.createElement("label"); label.className = "find-setting";
    const title = document.createElement("span"); title.textContent = field.label;
    const input = document.createElement("input"); input.type = "number"; input.min = "0"; input.max = "100"; input.step = "any"; input.required = true;
    input.id = "findV6-" + field.key; input.setAttribute("aria-label", field.label + " (%)");
    input.value = String(Math.round(V6_DEFAULT_CONFIG[field.key] * 100));
    const help = document.createElement("small"); help.id = input.id + "-help"; help.textContent = field.help;
    input.setAttribute("aria-describedby", help.id);
    input.addEventListener("input", () => {
      if (state.findBusy) return;
      if (validV6Settings()) state.findV6Config = Object.fromEntries(V6_SETTINGS.map(({key}) => [key, $("#findV6-" + key).valueAsNumber / 100]));
      onChange();
    });
    const value = document.createElement("span"); value.className = "find-setting-value";
    const unit = document.createElement("span"); unit.textContent = "%"; unit.setAttribute("aria-hidden", "true");
    value.append(input, unit);
    label.append(title, value, help); container.append(label);
  }
  $("#findV6SettingsReset").addEventListener("click", () => {
    if (state.findBusy) return;
    state.findV6Config = {};
    for (const {key} of V6_SETTINGS) $("#findV6-" + key).value = String(Math.round(V6_DEFAULT_CONFIG[key] * 100));
    onChange();
  });
}
export function renderV6Settings(result) {
  const active = state.findMode === "all" && state.findVersion === "v6";
  $("#findV6Settings").classList.toggle("hidden", !active);
  $("#findV6SettingsFields").disabled = state.findBusy;
  const valid = validV6Settings();
  $("#findV6SettingsError").textContent = valid ? "" : "Enter a percentage from 0 to 100 for every setting.";
  $("#findV6SettingsError").classList.toggle("hidden", !active || valid);
  $("#findV6SettingsState").textContent = valid ? (isCustomV6Config(resolveV6Config(state.findV6Config)) ? "Custom" : "Defaults") : "Invalid";
  if (active && !valid) $("#findObjectButton").disabled = true;
  const config = result?.version === "v6" ? result.config : null;
  $("#findRunSettings").classList.toggle("hidden", !config);
  $("#findRunSettingsSummary").textContent = "Settings used for this result · " + (config && isCustomV6Config(config) ? "Custom" : "Defaults");
  $("#findRunConfigData").textContent = config ? JSON.stringify(config, null, 2) : "";
}
