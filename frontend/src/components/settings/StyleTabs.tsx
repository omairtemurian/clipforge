import { useState } from "react";
import { useBrandTemplates, useCaptionTemplates } from "@/api/templates";
import type { ProcessingSettings } from "@/api/types";
import { CaptionCarousel } from "./CaptionCarousel";
import { CaptionColorsField } from "./CaptionColorsField";
import { Field } from "./Field";
import { NativeSelect } from "@/components/ui/native-select";
import { MyPresets } from "./MyPresets";
import { PanelTabs } from "./PanelTabs";
import { DefaultLayoutField } from "./DefaultLayoutField";
import { CameraMotionField } from "./CameraMotionField";
import { ReframeStyleField } from "./ReframeStyleField";
import { ZoomOutMoments } from "./ZoomOutMoments";
import { ASPECTS, ZOOMS_OUT } from "@/lib/processingSettings";

interface StyleTabsProps {
  settings: ProcessingSettings;
  onChange: (patch: Partial<ProcessingSettings>) => void;
}

/** The look of the clips ("Presets": captions, aspect ratio and brand) and
 * the owner's saved panels ("My presets"). */
export function StyleTabs({ settings, onChange }: StyleTabsProps) {
  const captions = useCaptionTemplates();
  const brands = useBrandTemplates();
  const [tab, setTab] = useState<"presets" | "mine">("presets");

  const presets = (
    <div className="flex flex-col gap-5">
      <Field label="Caption style">
        <CaptionCarousel
          layout="grid"
          templates={captions.data}
          value={settings.caption_template}
          onChange={(caption_template) =>
            onChange({ caption_template, captions: true })
          }
          captionsOff={!settings.captions}
          onCaptionsOff={() => onChange({ captions: false })}
        />
      </Field>
      <Field label="Caption colors">
        <CaptionColorsField
          template={
            captions.data?.find(
              (info) => info.name === settings.caption_template,
            )?.template
          }
          value={settings.caption_colors}
          onChange={(caption_colors) => onChange({ caption_colors })}
        />
      </Field>
      <div className="grid grid-cols-2 gap-x-6">
        <Field label="Aspect ratio" htmlFor="settings-aspect">
          <NativeSelect
            id="settings-aspect"
            value={settings.aspect}
            onChange={(event) =>
              onChange({
                aspect: event.target.value as ProcessingSettings["aspect"],
              })
            }
            block
          >
            {!ASPECTS.some((aspect) => aspect.value === settings.aspect) && (
              <option value={settings.aspect}>{settings.aspect} custom</option>
            )}
            {ASPECTS.map((aspect) => (
              <option key={aspect.value} value={aspect.value}>
                {aspect.label}
              </option>
            ))}
          </NativeSelect>
        </Field>
        <Field label="Brand template" htmlFor="settings-brand">
          <NativeSelect
            id="settings-brand"
            value={settings.brand_template_id ?? ""}
            onChange={(event) =>
              onChange({
                brand_template_id: event.target.value
                  ? Number(event.target.value)
                  : null,
              })
            }
            block
          >
            <option value="">None</option>
            {brands.data?.map((brand) => (
              <option key={brand.id} value={brand.id}>
                {brand.name}
              </option>
            ))}
          </NativeSelect>
        </Field>
      </div>
      <ReframeStyleField settings={settings} onChange={onChange} />
      <CameraMotionField
        value={settings.camera_motion}
        onChange={(camera_motion) => onChange({ camera_motion })}
      />
      <DefaultLayoutField settings={settings} onChange={onChange} />
      <ZoomOutMoments
        value={settings.zoom_out_moments}
        onChange={(zoom_out_moments) => onChange({ zoom_out_moments })}
        disabled={!ZOOMS_OUT.includes(settings.default_layout)}
        hint={
          ZOOMS_OUT.includes(settings.default_layout)
            ? undefined
            : "Needs the Automatic or Switch per segment layout"
        }
      />
    </div>
  );

  return (
    <PanelTabs
      label="Clip style"
      value={tab}
      onChange={setTab}
      tabs={[
        { value: "presets", label: "Presets", content: presets },
        {
          value: "mine",
          label: "My presets",
          content: (
            <MyPresets
              settings={settings}
              onApply={(saved) =>
                onChange({
                  ...saved,
                  timeframe_start: settings.timeframe_start,
                  timeframe_end: settings.timeframe_end,
                  subtitles_id: settings.subtitles_id,
                })
              }
            />
          ),
        },
      ]}
    />
  );
}
