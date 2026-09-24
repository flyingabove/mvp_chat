/* Reusable atlas UI. Story facts, locations, geometry and routes come from the API. */
(function (root) {
  "use strict";
  function regionalArea(atlas, id) {
    const areas = new Map(atlas.areas.map((a) => [a.id, a]));
    let area = areas.get(id);
    const seen = new Set();
    while (area && area.parent_id && !seen.has(area.id)) {
      seen.add(area.id);
      area = areas.get(area.parent_id);
    }
    return area;
  }
  function routeBetween(routes, from, to) {
    const best = new Map([[from, 0]]),
      paths = new Map([[from, []]]),
      queue = [[0, from]];
    while (queue.length) {
      queue.sort((a, b) => a[0] - b[0]);
      const [cost, id] = queue.shift();
      if (cost !== best.get(id)) continue;
      if (id === to) return { minutes: cost, segments: paths.get(id) };
      routes
        .filter((e) => e.from === id && !e.blocked)
        .forEach((e) => {
          const next = cost + e.minutes;
          if (next < (best.get(e.to) ?? Infinity)) {
            best.set(e.to, next);
            paths.set(e.to, paths.get(id).concat(e));
            queue.push([next, e.to]);
          }
        });
    }
    return null;
  }
  function project(point, bounds, width = 900, height = 540) {
    const scale = Math.min(
      (width - 100) / (bounds.maxX - bounds.minX),
      (height - 100) / (bounds.maxY - bounds.minY),
    );
    return {
      x: width / 2 + (point.x - (bounds.minX + bounds.maxX) / 2) * scale,
      y: height / 2 - (point.y - (bounds.minY + bounds.maxY) / 2) * scale,
    };
  }
  function element(tag, text, cls) {
    const el = document.createElement(tag);
    if (text !== undefined) el.textContent = text;
    if (cls) el.className = cls;
    return el;
  }
  function svgElement(tag, attrs, text) {
    const el = document.createElementNS("http://www.w3.org/2000/svg", tag);
    Object.entries(attrs).forEach(([key, value]) =>
      el.setAttribute(key, value),
    );
    if (text !== undefined) el.textContent = text;
    return el;
  }
  class WorldMapView {
    constructor(host, atlas, imageUrl) {
      this.host = host;
      this.atlas = atlas;
      this.imageUrl = imageUrl;
      this.mode = imageUrl ? "Artwork" : "Regions";
      this.selected = null;
      this.interiorArea = atlas.locations.find((l) => l.map_position)?.area_id;
      this.render();
    }
    render() {
      this.host.replaceChildren();
      const title = element("h2", this.atlas.title),
        toolbar = element("div", undefined, "atlas-toolbar");
      ["Artwork", "Regions", "Nearby", "Interiors"].forEach((mode) => {
        if (mode === "Artwork" && !this.imageUrl) return;
        if (
          mode === "Interiors" &&
          !this.atlas.locations.some((l) => l.map_position)
        )
          return;
        const button = element("button", mode);
        button.type = "button";
        button.setAttribute("aria-pressed", String(this.mode === mode));
        button.onclick = () => {
          this.mode = mode;
          this.render();
        };
        toolbar.append(button);
      });
      this.host.append(title, toolbar);
      if (this.mode === "Interiors") {
        const selector = element("select");
        selector.setAttribute("aria-label", "Interior area");
        this.atlas.areas
          .filter((a) =>
            this.atlas.locations.some(
              (l) => l.area_id === a.id && l.map_position,
            ),
          )
          .forEach((a) => selector.append(new Option(a.name, a.id)));
        selector.value = this.interiorArea;
        selector.onchange = () => {
          this.interiorArea = selector.value;
          this.render();
        };
        this.host.append(selector);
      }
      const stage = element("div", undefined, "atlas-stage");
      if (this.mode === "Artwork") {
        const image = element("img");
        image.src = this.imageUrl;
        image.alt = this.atlas.title + " illustrated atlas";
        const zoom = element("button", "Enlarge artwork", "atlas-zoom");
        zoom.type = "button";
        zoom.onclick = () => {
          stage.classList.toggle("enlarged");
          zoom.textContent = stage.classList.contains("enlarged")
            ? "Fit artwork"
            : "Enlarge artwork";
        };
        stage.append(image);
        this.host.append(zoom);
      } else {
        stage.append(this.drawMap());
      }
      this.host.append(stage);
      const caption =
        this.mode === "Interiors"
          ? "Choose a room to explore."
          : this.mode === "Artwork"
            ? "Explore the city and your shared home."
            : `North ↑ · East → · Kilometers from ${this.atlas.origin_label}. Choose a neighborhood to explore.`;
      this.host.append(element("p", caption, "atlas-caption"));
      const controls = element("div", undefined, "atlas-controls");
      this.filter = element("select");
      this.filter.setAttribute("aria-label", "Filter locations by region");
      this.filter.append(new Option("All regions", ""));
      this.atlas.areas.forEach((a) =>
        this.filter.append(
          new Option((a.parent_id ? "↳ " : "") + a.name, a.id),
        ),
      );
      this.search = element("input");
      this.search.type = "search";
      this.search.placeholder = "Find a room or venue";
      this.search.setAttribute("aria-label", "Search map locations");
      this.filter.onchange = this.search.oninput = () => this.renderList();
      controls.append(this.filter, this.search);
      this.host.append(controls);
      this.list = element("div", undefined, "atlas-list");
      this.detail = element("div", undefined, "atlas-detail");
      this.detail.setAttribute("aria-live", "polite");
      this.host.append(this.list, this.detail);
      this.renderList();
      if (this.selected) this.selectLocation(this.selected, false);
      this.host.scrollTop = 0;
    }
    drawMap() {
      const svg = svgElement("svg", {
        viewBox: "0 0 900 540",
        role: "img",
        "aria-label": this.mode + " map",
      });
      let points;
      if (this.mode === "Interiors") {
        points = this.atlas.locations
          .filter((l) => l.map_position && l.area_id === this.interiorArea)
          .map((l) => ({ id: l.id, name: l.name, point: l.map_position }));
        // Indoor y increases downward, unlike northing on the regional map.
        points.forEach((p) => {
          p.point = { x: p.point.x, y: 100 - p.point.y };
        });
      } else {
        points = this.atlas.areas
          .filter((a) => !a.parent_id && a.position)
          .map((a) => ({ id: a.id, name: a.name, point: a.position, area: a }));
        if (this.mode === "Nearby")
          points = points.filter(
            (p) =>
              Math.hypot(p.point.x, p.point.y) <= this.atlas.nearby_radius_km,
          );
      }
      if (!points.length) return svg;
      const bounds = {
        minX: Math.min(...points.map((p) => p.point.x)) - 3,
        maxX: Math.max(...points.map((p) => p.point.x)) + 3,
        minY: Math.min(...points.map((p) => p.point.y)) - 3,
        maxY: Math.max(...points.map((p) => p.point.y)) + 3,
      };
      const positions = new Map(
        points.map((p) => [p.id, project(p.point, bounds)]),
      );
      const origin = project({ x: 0, y: 0 }, bounds);
      if (this.mode !== "Interiors") {
        svg.append(
          svgElement("line", {
            x1: origin.x,
            x2: origin.x,
            y1: 20,
            y2: 520,
            class: "atlas-axis",
          }),
          svgElement("line", {
            x1: 20,
            x2: 880,
            y1: origin.y,
            y2: origin.y,
            class: "atlas-axis",
          }),
        );
        const step = this.mode === "Nearby" ? 5 : 20;
        for (
          let x = Math.ceil(bounds.minX / step) * step;
          x <= bounds.maxX;
          x += step
        ) {
          const p = project({ x, y: 0 }, bounds);
          svg.append(
            svgElement(
              "text",
              { x: p.x, y: origin.y + 20, class: "atlas-tick" },
              `${x} km`,
            ),
          );
        }
        for (
          let y = Math.ceil(bounds.minY / step) * step;
          y <= bounds.maxY;
          y += step
        ) {
          if (y === 0) continue;
          const p = project({ x: 0, y }, bounds);
          svg.append(
            svgElement(
              "text",
              { x: origin.x + 10, y: p.y, class: "atlas-tick" },
              `${y} km`,
            ),
          );
        }
      } else {
        this.atlas.routes
          .filter(
            (e) =>
              e.from < e.to && positions.has(e.from) && positions.has(e.to),
          )
          .forEach((e) => {
            const a = positions.get(e.from),
              b = positions.get(e.to);
            svg.append(
              svgElement("line", {
                x1: a.x,
                y1: a.y,
                x2: b.x,
                y2: b.y,
                class: "atlas-route",
              }),
            );
          });
      }
      points.forEach((p, index) => {
        const xy = positions.get(p.id),
          group = svgElement("g", {
            tabindex: "0",
            role: "button",
            "aria-label": p.name,
            class: "atlas-marker",
          });
        const label =
          p.area && p.area.distance_min_km != null
            ? `${p.name} · ${p.area.distance_min_km}${p.area.distance_min_km !== p.area.distance_max_km ? "–" + p.area.distance_max_km : ""} km`
            : p.name;
        group.append(
          svgElement("title", {}, label),
          svgElement("circle", {
            cx: xy.x,
            cy: xy.y,
            r: 25,
            class: "atlas-hit",
          }),
          svgElement("circle", { cx: xy.x, cy: xy.y, r: 7 }),
        );
        // Short numbered markers stay readable where nearby clusters overlap; labels live in the list.
        group.append(
          svgElement("text", { x: xy.x + 11, y: xy.y - 10 }, String(index + 1)),
        );
        const activate = () => {
          if (this.mode === "Interiors") this.selectLocation(p.id);
          else {
            this.filter.value = p.id;
            this.renderList();
            this.detail.replaceChildren(
              element("h3", label),
              element("p", "Explore places in this neighborhood."),
            );
          }
        };
        group.onclick = activate;
        group.onkeydown = (e) => {
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            activate();
          }
        };
        svg.append(group);
      });
      if (this.mode !== "Interiors") {
        // An adjacent HTML legend is accessible and scales without text collisions.
        const legend = svgElement(
          "text",
          { x: 22, y: 28, class: "atlas-tick" },
          "Select a numbered marker; use Nearby for the nearby clusters.",
        );
        svg.append(legend);
      }
      this.mapPoints = points;
      return svg;
    }
    renderList() {
      const areaId = this.filter.value,
        query = this.search.value.toLowerCase();
      this.list.replaceChildren();
      if (this.mode !== "Artwork" && this.mapPoints) {
        const legend = element("div", undefined, "atlas-legend");
        this.mapPoints.forEach((p, i) => {
          const button = element("button", `${i + 1}. ${p.name}`);
          button.type = "button";
          button.onclick = () => {
            if (this.mode === "Interiors") this.selectLocation(p.id);
            else {
              this.filter.value = p.id;
              this.renderList();
            }
          };
          legend.append(button);
        });
        this.list.append(legend);
      }
      const matches = this.atlas.locations.filter((l) => {
        const regional = regionalArea(this.atlas, l.area_id);
        return (
          (!areaId || l.area_id === areaId || regional?.id === areaId) &&
          `${l.name} ${l.research.source_ids.join(" ")}`
            .toLowerCase()
            .includes(query)
        );
      });
      this.list.append(element("p", `${matches.length} places`));
      matches.forEach((l) => {
        const button = element(
          "button",
          l.name,
          "atlas-place",
        );
        button.type = "button";
        button.onclick = () => this.selectLocation(l.id);
        this.list.append(button);
      });
    }
    selectLocation(id, reveal = true) {
      const loc = this.atlas.locations.find((l) => l.id === id);
      if (!loc) return;
      this.selected = id;
      this.detail.replaceChildren(
        element("h3", loc.name),
        element("p", loc.description),
      );
      const label = element("label", "Plan route from: "),
        select = element("select");
      select.setAttribute("aria-label", "Route origin");
      this.atlas.locations.forEach((l) =>
        select.append(new Option(l.name, l.id)),
      );
      const routeOutput = element("p");
      const show = () => {
        const route = routeBetween(this.atlas.routes, select.value, id),
          names = new Map(this.atlas.locations.map((l) => [l.id, l.name]));
        routeOutput.textContent = route
          ? `${route.minutes} min travel. ${[select.value, ...route.segments.map((e) => e.to)].map((l) => names.get(l)).join(" → ")}`
          : "No route available.";
      };
      select.onchange = show;
      label.append(select);
      this.detail.append(label, routeOutput);
      show();
      if (reveal) this.detail.scrollIntoView({ block: "nearest" });
    }
  }
  root.WorldMapView = WorldMapView;
  if (typeof module !== "undefined")
    module.exports = { regionalArea, routeBetween, project };
})(typeof window !== "undefined" ? window : globalThis);
