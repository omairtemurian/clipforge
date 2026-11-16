import { Link } from "react-router-dom";
import { useSetProjectBrand } from "@/api/clipActions";
import { useBrandTemplates } from "@/api/templates";
import type { Project } from "@/api/types";
import { Field } from "@/components/settings/Field";
import { NativeSelect } from "@/components/ui/native-select";

/**
 * The editor's Brand tab: the brand template (logo, font and color) of the
 * project's clips. Unlike the other panels it saves at once: the template
 * belongs to the whole project, not to this clip.
 */
export function BrandPanel({ project }: { project: Project }) {
  const brands = useBrandTemplates();
  const setBrand = useSetProjectBrand(project.id);
  const selected = project.settings.brand_template_id ?? null;
  const missing =
    selected !== null && !brands.data?.some((b) => b.id === selected);

  return (
    <div className="flex flex-col gap-3">
      <Field label="Brand template" htmlFor="brand-template">
        <NativeSelect
          id="brand-template"
          value={selected ?? ""}
          disabled={setBrand.isPending}
          onChange={(event) =>
            setBrand.mutate(
              event.target.value ? Number(event.target.value) : null,
            )
          }
          block
        >
          <option value="">None</option>
          {missing && <option value={selected}>Deleted template</option>}
          {brands.data?.map((brand) => (
            <option key={brand.id} value={brand.id}>
              {brand.name}
            </option>
          ))}
        </NativeSelect>
      </Field>
      <p className="text-caption text-muted-foreground">
        Applies to every clip of this project and is saved right away.
      </p>
      {brands.data?.length === 0 && (
        <p className="text-caption text-muted-foreground">
          No templates yet.{" "}
          <Link
            to="/brand-templates"
            className="text-primary-ink hover:underline"
          >
            Create a brand template
          </Link>
        </p>
      )}
    </div>
  );
}
