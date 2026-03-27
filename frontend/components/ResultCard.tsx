"use client";

import { EnrichedDeal } from "@/lib/types";
import { getFlagEmoji } from "@/lib/countries";

interface ResultCardProps {
  deal: EnrichedDeal;
  numPeople?: number;
}

function formatDate(dateStr: string): string {
  const d = new Date(dateStr + "T00:00:00");
  return d.toLocaleDateString("en-GB", { day: "numeric", month: "short" });
}

function FlightLine({
  label,
  flight,
  isHome,
  googleFlightsUrl,
}: {
  label: string;
  flight: EnrichedDeal["outbound_flight"];
  isHome: boolean;
  googleFlightsUrl: string | null;
}) {
  if (isHome) {
    return (
      <div className="flex items-center gap-2 text-sm text-success">
        <span>&#x1F3E0;</span>
        <span>
          {label === "Out" ? "Drive from home" : "Drive home"} &mdash;
          &pound;0
        </span>
      </div>
    );
  }

  if (!flight) {
    return (
      <div className="flex items-center gap-2 text-sm text-text-muted/60 italic">
        <span>&#x2708;&#xFE0F;</span>
        <span className="animate-pulse">Searching flights...</span>
      </div>
    );
  }

  return (
    <div className="flex items-center gap-2 text-sm text-text">
      <span>&#x2708;&#xFE0F;</span>
      <span className="font-medium">{flight.airline}</span>
      <span className="text-text-muted">
        {flight.departure_airport}&rarr;{flight.arrival_airport}
      </span>
      <span className="text-text-muted">{flight.departure_time}</span>
      <span className="font-semibold text-primary">
        &pound;{Math.round(flight.price_gbp)}
      </span>
      {googleFlightsUrl && (
        <a
          href={googleFlightsUrl}
          target="_blank"
          rel="noopener noreferrer"
          className="ml-auto text-xs text-primary/60 hover:text-primary underline"
        >
          check
        </a>
      )}
    </div>
  );
}

export default function ResultCard({ deal, numPeople = 1 }: ResultCardProps) {
  const { deal: info, total_price_gbp } = deal;
  const isIncomplete = total_price_gbp === null;

  // Per-person price: flights are per person, van hire is split
  const perPersonPrice =
    total_price_gbp !== null
      ? Math.round(
          (total_price_gbp - info.imoova_price_gbp) +
          info.imoova_price_gbp / numPeople
        )
      : null;

  const pickupFlag = getFlagEmoji(info.pickup_country);
  const dropoffFlag = getFlagEmoji(info.dropoff_country);

  return (
    <div
      className={`relative rounded-xl border bg-white p-5 shadow-sm transition-all hover:shadow-md ${
        isIncomplete ? "border-slate-200 border-dashed" : "border-slate-200"
      }`}
    >
      {/* Total price badge */}
      <div className={`absolute -right-2 -top-2 rounded-xl px-3 py-1.5 text-lg font-bold text-white shadow-md ${
        isIncomplete ? "bg-slate-400 animate-pulse" : "bg-accent"
      }`}>
        {isIncomplete ? (
          <span className="text-sm font-normal">...</span>
        ) : (
          <span>
            &pound;{perPersonPrice}
            {numPeople > 1 && (
              <span className="text-xs font-normal opacity-80">/pp</span>
            )}
          </span>
        )}
      </div>

      {/* Route */}
      <div className="mb-3 pr-16">
        <div className="flex items-center gap-2 text-lg font-semibold text-text">
          <span>{pickupFlag}</span>
          <span>{info.pickup_city}</span>
          <span className="text-text-muted">&rarr;</span>
          <span>{dropoffFlag}</span>
          <span>{info.dropoff_city}</span>
        </div>
      </div>

      {/* Dates, drive time, and vehicle */}
      <div className="mb-3 flex flex-wrap gap-x-4 gap-y-1 text-sm text-text-muted">
        <span>
          {formatDate(info.pickup_date)} &ndash; {formatDate(info.dropoff_date)}{" "}
          ({info.drive_days} days)
        </span>
        {deal.drive_hours != null && (
          <span title="Estimated driving time">
            &#x1F697; ~{deal.drive_hours}h drive
          </span>
        )}
        <span>
          {info.vehicle_type}
          {info.seats > 0 && ` (${info.seats} seats)`}
        </span>
      </div>

      {/* Flight details */}
      <div className="mb-3 space-y-1.5 rounded-lg bg-slate-50 p-3">
        <FlightLine
          label="Out"
          flight={deal.outbound_flight}
          isHome={deal.outbound_is_home}
          googleFlightsUrl={deal.google_flights_outbound_url}
        />
        <FlightLine
          label="Return"
          flight={deal.return_flight}
          isHome={deal.return_is_home}
          googleFlightsUrl={deal.google_flights_return_url}
        />
      </div>

      {/* Imoova price */}
      <div className="mb-4 text-sm text-text-muted">
        Imoova relocation: &pound;{Math.round(info.imoova_price_gbp)}
        {numPeople > 1 && (
          <span className="text-primary">
            {" "}(&pound;{Math.round(info.imoova_price_gbp / numPeople)}/pp)
          </span>
        )}
      </div>

      {/* Action buttons */}
      <div className="flex gap-2">
        <a
          href={info.imoova_url}
          target="_blank"
          rel="noopener noreferrer"
          className="flex-1 rounded-lg bg-primary px-3 py-2 text-center text-sm font-medium text-white
            transition-colors hover:bg-primary-dark"
        >
          Book Campervan
        </a>
        {deal.google_flights_outbound_url && (
          <a
            href={deal.google_flights_outbound_url}
            target="_blank"
            rel="noopener noreferrer"
            className="flex-1 rounded-lg border border-primary px-3 py-2 text-center text-sm
              font-medium text-primary transition-colors hover:bg-primary/5"
          >
            Check Flights
          </a>
        )}
      </div>
    </div>
  );
}
