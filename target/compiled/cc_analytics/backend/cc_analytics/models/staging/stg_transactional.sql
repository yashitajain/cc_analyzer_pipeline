with source as (
    select * from "postgres"."public"."raw_transactions"
),
cleaned as (
    select 
        date,
        merchant,
        category,
        cast(amount as decimal(10,2)) as amount,
        is_credit
        from source
        where amount > 0
)
select * from cleaned